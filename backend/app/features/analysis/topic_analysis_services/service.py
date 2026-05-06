"""Orchestrates the full topic-analysis pipeline: validation, text prep, community detection, labelling, and translation."""
from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, replace

import pandas as pd

from app.core.exceptions import TopicAnalysisError, TopicAnalysisInputError, TopicAnalysisRateLimitError
from app.features.analysis.topic_analysis_services.community_detection_service import (
    CommunityDetectionAnalysisService,
)
from app.features.analysis.topic_analysis_services.config import (
    PreparedDocument,
    PreparedTextDataset,
    TopicAnalysisConfig,
)
from app.features.analysis.topic_analysis_services.contracts import (
    AnalysisGroupRecord,
    AnalysisNetworkEdgeRecord,
    AnalysisRunResult,
    AnalysisScatterPointRecord,
)
from app.features.analysis.topic_analysis_services.embedding_service import SentenceEmbeddingService
from app.features.analysis.topic_analysis_services.example_selection_service import (
    RepresentativeExampleSelectionService,
)
from app.features.analysis.topic_analysis_services.execution import (
    TopicModelExecutionService,
)
from app.features.analysis.topic_analysis_services.group_assembly_service import (
    TopicGroupAssemblyService,
)
from app.features.analysis.topic_analysis_services.keyword_service import TopicAnalysisKeywordService
from app.features.analysis.topic_analysis_services.narrative_service import TopicAnalysisNarrativeService
from app.features.analysis.topic_analysis_services.ngram_service import NgramAnalysisService
from app.features.analysis.topic_analysis_services.output_translation_service import (
    TopicAnalysisOutputTranslationService,
)
from app.features.analysis.topic_analysis_services.text_preparation_service import TopicAnalysisTextPreparationService
from app.features.analysis.topic_analysis_services.validation_service import TopicAnalysisInputValidationService
from app.features.common.protocols import TopicLabelServiceProtocol
from app.models.enums import AnalysisModelKey

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _PreparedAnalysisRun:
    prepared: PreparedTextDataset
    result: AnalysisRunResult


class TopicAnalysisService:
    """End-to-end topic analysis service that routes to community detection or n-grams."""

    def __init__(
        self,
        *,
        config: TopicAnalysisConfig,
        input_validation_service: TopicAnalysisInputValidationService,
        text_preparation_service: TopicAnalysisTextPreparationService,
        keyword_service: TopicAnalysisKeywordService,
        narrative_service: TopicAnalysisNarrativeService,
        representative_example_service: RepresentativeExampleSelectionService,
        embedding_service: SentenceEmbeddingService,
        ngram_service: NgramAnalysisService,
        community_detection_service: CommunityDetectionAnalysisService,
        ai_label_service: TopicLabelServiceProtocol | None = None,
    ) -> None:
        self.config = config
        self.input_validation_service = input_validation_service
        self.text_preparation_service = text_preparation_service
        self.ngram_service = ngram_service
        self.model_execution_service = TopicModelExecutionService(
            config=config,
            embedding_service=embedding_service,
            community_detection_service=community_detection_service,
        )
        self.group_assembly_service = TopicGroupAssemblyService(
            config=config,
            keyword_service=keyword_service,
            narrative_service=narrative_service,
            representative_example_service=representative_example_service,
            translation_service=text_preparation_service.translation_service,
        )
        self.output_translation_service = TopicAnalysisOutputTranslationService(
            keyword_service=keyword_service,
            narrative_service=narrative_service,
            translation_service=text_preparation_service.translation_service,
            ai_label_service=ai_label_service,
        )

    def warm_up(self) -> None:
        self.text_preparation_service.warm_up()
        self.model_execution_service.warm_up()

    def cleanup_expired_user_data(self) -> dict[str, int]:
        translation_cache_entries = 0
        translation_service = self.text_preparation_service.translation_service
        if translation_service is not None:
            cleanup = getattr(translation_service, "cleanup_expired", None)
            if callable(cleanup):
                translation_cache_entries = int(cleanup())

        embedding_cache_entries = self.model_execution_service.cleanup_expired()
        return {
            "translation_cache_entries": translation_cache_entries,
            "embedding_cache_entries": embedding_cache_entries,
        }

    def run(
        self,
        *,
        result_id: str,
        dataframe: pd.DataFrame,
        model_key: AnalysisModelKey,
        text_column_name: str,
        available_verbatim_columns: Iterable[str],
        community_similarity_threshold: float | None = None,
    ) -> AnalysisRunResult:
        base_result = AnalysisRunResult.empty(
            result_id=result_id,
            model_key=model_key,
            text_column_name=text_column_name,
            filtered_row_count=int(len(dataframe)),
        )
        if model_key == AnalysisModelKey.COMMUNITY:
            base_result.community_similarity_threshold = self._normalize_community_similarity_threshold(
                community_similarity_threshold
            )

        try:
            prepared_run = self._prepare_run(
                base_result=base_result,
                dataframe=dataframe,
                model_key=model_key,
                text_column_name=text_column_name,
                available_verbatim_columns=available_verbatim_columns,
            )
            if model_key == AnalysisModelKey.NGRAMS:
                return self._run_ngram_analysis(prepared_run)
            return self._run_grouped_analysis(
                prepared_run=prepared_run,
                model_key=model_key,
                text_column_name=text_column_name,
                community_similarity_threshold=community_similarity_threshold,
            )
        except TopicAnalysisError as exc:
            if isinstance(exc, TopicAnalysisInputError):
                logger.info(
                    "Topic analysis input rejected for result_id=%s model=%s column=%s: %s",
                    result_id,
                    model_key.value,
                    text_column_name,
                    exc,
                )
            elif isinstance(exc, TopicAnalysisRateLimitError):
                logger.warning(
                    "Topic analysis hit a retryable provider rate limit for result_id=%s model=%s column=%s: %s",
                    result_id,
                    model_key.value,
                    text_column_name,
                    exc,
                )
                return self._build_error_response(
                    base_result,
                    str(exc),
                    error_code=exc.error_code,
                    retry_after_seconds=exc.retry_after_seconds,
                )
            else:
                logger.warning(
                    "Topic analysis failed for result_id=%s model=%s column=%s (%s: %s).",
                    result_id,
                    model_key.value,
                    text_column_name,
                    type(exc).__name__,
                    exc,
                )
            return self._build_error_response(base_result, str(exc))
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.exception(
                "Topic analysis crashed unexpectedly for result_id=%s model=%s column=%s.",
                result_id,
                model_key.value,
                text_column_name,
            )
            return self._build_error_response(base_result, f"Analysis failed unexpectedly: {exc}")

    def _prepare_run(
        self,
        *,
        base_result: AnalysisRunResult,
        dataframe: pd.DataFrame,
        model_key: AnalysisModelKey,
        text_column_name: str,
        available_verbatim_columns: Iterable[str],
    ) -> _PreparedAnalysisRun:
        self.input_validation_service.validate_request(
            model_key=model_key,
            text_column_name=text_column_name,
            available_verbatim_columns=available_verbatim_columns,
        )
        prepared = self.text_preparation_service.prepare(
            dataframe,
            text_column_name=text_column_name,
        )
        warnings = self.input_validation_service.validate_dataset(
            prepared,
            model_key=model_key,
        )
        result = replace(
            base_result,
            valid_document_count=int(len(prepared.documents)),
            original_response_count=int(prepared.original_response_count),
            skipped_document_count=int(prepared.skipped_row_count),
            warnings=warnings,
        )
        return _PreparedAnalysisRun(prepared=prepared, result=result)

    def _run_ngram_analysis(self, prepared_run: _PreparedAnalysisRun) -> AnalysisRunResult:
        ngram_buckets = self.ngram_service.run(
            prepared_run.prepared.documents,
            top_n=self.config.top_ngrams_per_bucket,
        )
        translated_bucket_count, translation_warnings = self.output_translation_service.translate_ngram_buckets(ngram_buckets)
        warnings = list(prepared_run.result.warnings)
        warnings.extend(translation_warnings)
        return replace(
            prepared_run.result,
            ok=True,
            translated_document_count=prepared_run.prepared.translated_document_count + translated_bucket_count,
            warnings=warnings,
            ngram_buckets=ngram_buckets,
        )

    def _run_grouped_analysis(
        self,
        *,
        prepared_run: _PreparedAnalysisRun,
        model_key: AnalysisModelKey,
        text_column_name: str,
        community_similarity_threshold: float | None,
    ) -> AnalysisRunResult:
        normalized_threshold = self._normalize_community_similarity_threshold(community_similarity_threshold)
        execution = self.model_execution_service.execute(
            model_key=model_key,
            texts=list(prepared_run.prepared.texts),
            languages=[
                None if document.translated_to_english else document.detected_language
                for document in prepared_run.prepared.documents
            ],
            community_similarity_threshold=normalized_threshold,
        )
        warnings = list(prepared_run.result.warnings)
        warnings.extend(execution.warnings or [])
        warnings.extend(execution.result.warnings)

        groups = self.group_assembly_service.build_groups(
            documents=prepared_run.prepared.documents,
            assignments=execution.result.assignments,
            explicit_groups=execution.result.groups,
            network_edges=execution.result.network_edges,
            model_key=model_key.value,
        )
        _, ai_warnings = self.output_translation_service.apply_ai_labels(
            groups,
            model_key=model_key,
            text_column_name=text_column_name,
        )
        warnings.extend(ai_warnings)
        translated_group_count, translation_warnings = self.output_translation_service.translate_group_outputs(groups)
        warnings.extend(translation_warnings)
        groups, group_id_aliases = self._merge_duplicate_label_groups(groups)
        scatter_points, network_edges = self._build_community_plot_records(
            documents=prepared_run.prepared.documents,
            assignments=execution.result.assignments,
            groups=groups,
            group_id_aliases=group_id_aliases,
            layout_positions=execution.result.layout_positions,
            network_edges=execution.result.network_edges,
        )

        return replace(
            prepared_run.result,
            ok=True,
            translated_document_count=prepared_run.prepared.translated_document_count + translated_group_count,
            community_similarity_threshold=normalized_threshold,
            warnings=warnings,
            groups=groups,
            scatter_points=scatter_points,
            network_edges=network_edges,
        )

    @staticmethod
    def _build_error_response(
        base_result: AnalysisRunResult,
        message: str,
        *,
        error_code: str | None = None,
        retry_after_seconds: int | None = None,
    ) -> AnalysisRunResult:
        return replace(
            base_result,
            error=message,
            error_code=error_code,
            retry_after_seconds=retry_after_seconds,
        )

    @staticmethod
    def _build_community_plot_records(
        *,
        documents: list[PreparedDocument],
        assignments: list[int],
        groups: list[AnalysisGroupRecord],
        group_id_aliases: dict[str, str] | None = None,
        layout_positions: dict[int, tuple[float, float]],
        network_edges: list[tuple[int, int, float]],
    ) -> tuple[list[AnalysisScatterPointRecord], list[AnalysisNetworkEdgeRecord]]:
        group_labels = {str(group.group_id): group.label for group in groups}
        aliases = {str(source): str(target) for source, target in (group_id_aliases or {}).items()}
        scatter_points: list[AnalysisScatterPointRecord] = []
        row_numbers_by_node: dict[int, int] = {}
        for node_index, (document, assignment) in enumerate(zip(documents, assignments)):
            row_number = int(document.row_number)
            if row_number <= 0:
                continue
            row_numbers_by_node[node_index] = row_number
            position = layout_positions.get(node_index)
            if position is None:
                continue
            original_group_id = str(int(assignment))
            group_id = aliases.get(original_group_id, original_group_id)
            scatter_points.append(
                AnalysisScatterPointRecord(
                    point_index=int(node_index),
                    row_number=row_number,
                    text=document.text,
                    source_text=document.original_text,
                    group_id=group_id,
                    group_label=group_labels.get(group_id, f"Community {original_group_id}"),
                    x=float(position[0]),
                    y=float(position[1]),
                )
            )

        edge_records: list[AnalysisNetworkEdgeRecord] = []
        for source_node, target_node, weight in network_edges:
            source_row_number = row_numbers_by_node.get(int(source_node))
            target_row_number = row_numbers_by_node.get(int(target_node))
            if source_row_number is None or target_row_number is None:
                continue
            edge_records.append(
                AnalysisNetworkEdgeRecord(
                    source_point_index=int(source_node),
                    target_point_index=int(target_node),
                    source_row_number=source_row_number,
                    target_row_number=target_row_number,
                    weight=float(weight),
                )
            )
        return scatter_points, edge_records

    def _merge_duplicate_label_groups(
        self,
        groups: list[AnalysisGroupRecord],
    ) -> tuple[list[AnalysisGroupRecord], dict[str, str]]:
        if not groups:
            return [], {}

        grouped_by_label: dict[tuple[str, bool], list[AnalysisGroupRecord]] = {}
        for group in groups:
            normalized_label = self._normalize_group_label(group.label)
            if not normalized_label:
                normalized_label = str(group.group_id).strip()
            key = (normalized_label, bool(group.is_noise))
            grouped_by_label.setdefault(key, []).append(group)

        aliases: dict[str, str] = {}
        merged_groups: list[AnalysisGroupRecord] = []
        for _key, matching_groups in grouped_by_label.items():
            primary = matching_groups[0]
            primary_id = str(primary.group_id)
            for group in matching_groups:
                aliases[str(group.group_id)] = primary_id

            if len(matching_groups) == 1:
                merged_groups.append(primary)
                continue

            documents = [
                document
                for group in matching_groups
                for document in group.documents
            ]
            examples = [
                example
                for group in matching_groups
                for example in group.examples
            ]
            terms = self._merge_unique_terms(
                term
                for group in matching_groups
                for term in group.terms
            )
            count = sum(int(group.count or len(group.documents)) for group in matching_groups)

            merged_groups.append(
                AnalysisGroupRecord(
                    group_id=primary_id,
                    label=primary.label,
                    source_label=primary.source_label,
                    translated=any(group.translated for group in matching_groups),
                    ai_generated=any(group.ai_generated for group in matching_groups),
                    count=count,
                    share=0.0,
                    total_documents=0,
                    terms=terms,
                    examples=examples[: self.config.representative_examples_per_group],
                    is_noise=primary.is_noise,
                    documents=documents,
                    label_translation_warnings=[
                        warning
                        for group in matching_groups
                        for warning in group.label_translation_warnings
                    ],
                )
            )

        total_documents = max(1, sum(int(group.count or len(group.documents)) for group in merged_groups))
        for group in merged_groups:
            group.count = int(group.count or len(group.documents))
            group.share = round(group.count / total_documents, 4)
            group.total_documents = total_documents
            group.comment = self.output_translation_service.narrative_service.build_comment(
                label=group.label or "Group",
                count=group.count,
                total_documents=total_documents,
                examples=list(group.examples),
            )

        merged_groups.sort(key=lambda group: (-int(group.count), str(group.group_id)))
        return merged_groups, aliases

    @staticmethod
    def _normalize_group_label(label: str) -> str:
        return re.sub(r"\s+", " ", str(label or "").strip().casefold())

    @staticmethod
    def _merge_unique_terms(terms: Iterable[str]) -> list[str]:
        merged_terms: list[str] = []
        seen: set[str] = set()
        for term in terms:
            normalized = re.sub(r"\s+", " ", str(term or "").strip())
            key = normalized.casefold()
            if not normalized or key in seen:
                continue
            seen.add(key)
            merged_terms.append(normalized)
        return merged_terms

    def _normalize_community_similarity_threshold(self, value: float | None) -> float:
        if value is None:
            return float(self.config.community_similarity_threshold)
        return max(0.4, min(1.0, float(value)))
