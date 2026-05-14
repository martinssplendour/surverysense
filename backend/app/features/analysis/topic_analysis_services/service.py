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
    AnalysisDocumentRecord,
    AnalysisExampleRecord,
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
from app.features.common.document_relevance import DocumentRelevanceSorter
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
        logger.info(
            "Grouped analysis started: model=%s column=%s document_count=%s community_similarity_threshold=%.4f.",
            model_key.value,
            text_column_name,
            len(prepared_run.prepared.documents),
            normalized_threshold,
        )
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
        logger.info(
            "Model execution completed: model=%s column=%s assignment_count=%s execution_warning_count=%s.",
            model_key.value,
            text_column_name,
            len(execution.result.assignments),
            len(execution.warnings or []) + len(execution.result.warnings or []),
        )

        groups = self.group_assembly_service.build_groups(
            documents=prepared_run.prepared.documents,
            assignments=execution.result.assignments,
            explicit_groups=execution.result.groups,
            network_edges=execution.result.network_edges,
            model_key=model_key.value,
        )
        logger.info(
            "Initial group assembly completed: model=%s column=%s group_count=%s non_noise_group_count=%s.",
            model_key.value,
            text_column_name,
            len(groups),
            sum(1 for group in groups if not group.is_noise),
        )
        groups, top_term_aliases = self._merge_groups_by_top_term_signature(groups)
        logger.info(
            "Top-term signature merge completed: model=%s column=%s group_count=%s alias_count=%s.",
            model_key.value,
            text_column_name,
            len(groups),
            sum(1 for source, target in top_term_aliases.items() if source != target),
        )
        _, ai_warnings = self.output_translation_service.apply_ai_labels(
            groups,
            model_key=model_key,
            text_column_name=text_column_name,
        )
        warnings.extend(ai_warnings)
        logger.info(
            "AI label application completed: model=%s column=%s warning_count=%s ai_generated_group_count=%s.",
            model_key.value,
            text_column_name,
            len(ai_warnings),
            sum(1 for group in groups if group.ai_generated),
        )
        translated_group_count, translation_warnings = self.output_translation_service.translate_group_outputs(groups)
        warnings.extend(translation_warnings)
        logger.info(
            "Group output translation completed: model=%s column=%s translated_group_count=%s warning_count=%s.",
            model_key.value,
            text_column_name,
            translated_group_count,
            len(translation_warnings),
        )
        groups, label_aliases = self._merge_duplicate_label_groups(groups)
        group_id_aliases = self._compose_group_aliases(top_term_aliases, label_aliases)
        logger.info(
            "Label merge completed: model=%s column=%s group_count=%s alias_count=%s.",
            model_key.value,
            text_column_name,
            len(groups),
            sum(1 for source, target in label_aliases.items() if source != target),
        )
        self.group_assembly_service.order_group_outputs_by_label_relevance(groups)
        logger.info(
            "Response reranking completed: model=%s column=%s group_count=%s.",
            model_key.value,
            text_column_name,
            len(groups),
        )
        groups, weak_noise_row_numbers, weak_noise_count = self._move_off_topic_documents_to_noise(groups)
        if weak_noise_count:
            warnings.append(
                f"Moved {weak_noise_count} off-topic response(s) to unassigned noise because they did not match the topic label or top terms."
            )
        logger.info(
            "Off-topic noise reassignment completed: model=%s column=%s moved_response_count=%s group_count=%s.",
            model_key.value,
            text_column_name,
            weak_noise_count,
            len(groups),
        )
        self._refresh_group_comments(groups)
        scatter_points, network_edges = self._build_community_plot_records(
            documents=prepared_run.prepared.documents,
            assignments=execution.result.assignments,
            groups=groups,
            group_id_aliases=group_id_aliases,
            noise_row_numbers=weak_noise_row_numbers,
            layout_positions=execution.result.layout_positions,
            network_edges=execution.result.network_edges,
        )
        logger.info(
            "Grouped analysis completed: model=%s column=%s final_group_count=%s scatter_point_count=%s network_edge_count=%s warning_count=%s.",
            model_key.value,
            text_column_name,
            len(groups),
            len(scatter_points),
            len(network_edges),
            len(warnings),
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
        noise_row_numbers: set[int] | None = None,
        layout_positions: dict[int, tuple[float, float]],
        network_edges: list[tuple[int, int, float]],
    ) -> tuple[list[AnalysisScatterPointRecord], list[AnalysisNetworkEdgeRecord]]:
        group_labels = {str(group.group_id): group.label for group in groups}
        aliases = {str(source): str(target) for source, target in (group_id_aliases or {}).items()}
        noise_rows = {int(row_number) for row_number in (noise_row_numbers or set())}
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
            group_id = "-1" if row_number in noise_rows else aliases.get(original_group_id, original_group_id)
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
            logger.info("Label merge skipped: group_count=0.")
            return [], {}

        aliases: dict[str, str] = {}
        merged_groups: list[AnalysisGroupRecord] = []
        for matching_groups in self._group_by_matching_labels(groups):
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
                    term_strengths=self._merge_term_strengths(matching_groups, terms),
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
        logger.info(
            "Label merge details: input_group_count=%s output_group_count=%s merged_group_count=%s.",
            len(groups),
            len(merged_groups),
            sum(1 for source, target in aliases.items() if source != target),
        )
        return merged_groups, aliases

    def _merge_groups_by_top_term_signature(
        self,
        groups: list[AnalysisGroupRecord],
    ) -> tuple[list[AnalysisGroupRecord], dict[str, str]]:
        if not groups:
            logger.info("Top-term signature merge skipped: group_count=0.")
            return [], {}

        grouped_by_signature: dict[tuple[str, str], list[AnalysisGroupRecord]] = {}
        passthrough_groups: list[AnalysisGroupRecord] = []
        for group in groups:
            signature = self._top_term_signature(group)
            if group.is_noise or signature is None:
                passthrough_groups.append(group)
                continue
            grouped_by_signature.setdefault(signature, []).append(group)

        aliases: dict[str, str] = {}
        merged_groups: list[AnalysisGroupRecord] = list(passthrough_groups)
        for matching_groups in grouped_by_signature.values():
            matching_groups = sorted(matching_groups, key=lambda group: (-int(group.count or len(group.documents)), str(group.group_id)))
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
                    term_strengths=self._merge_term_strengths(matching_groups, terms),
                    examples=examples[: self.config.representative_examples_per_group],
                    is_noise=False,
                    documents=documents,
                    label_translation_warnings=[
                        warning
                        for group in matching_groups
                        for warning in group.label_translation_warnings
                    ],
                )
            )

        merged_signature_count = sum(1 for matching_groups in grouped_by_signature.values() if len(matching_groups) > 1)
        self._refresh_group_counts(merged_groups)
        logger.info(
            "Top-term signature merge details: signature_count=%s merged_signature_count=%s passthrough_group_count=%s output_group_count=%s.",
            len(grouped_by_signature),
            merged_signature_count,
            len(passthrough_groups),
            len(merged_groups),
        )
        return merged_groups, aliases

    @staticmethod
    def _top_term_signature(group: AnalysisGroupRecord) -> tuple[str, str] | None:
        ranked_terms = sorted(
            (
                (str(term), float(group.term_strengths.get(str(term), 0.0)), index)
                for index, term in enumerate(group.terms)
                if str(term).strip()
            ),
            key=lambda item: (-item[1], item[2], item[0]),
        )
        if len(ranked_terms) < 2:
            return None
        return tuple(sorted((ranked_terms[0][0].casefold(), ranked_terms[1][0].casefold())))

    @staticmethod
    def _merge_term_strengths(groups: list[AnalysisGroupRecord], terms: list[str]) -> dict[str, float]:
        weighted_scores: dict[str, float] = {}
        for group in groups:
            weight = max(1, int(group.count or len(group.documents) or 1))
            for term, strength in group.term_strengths.items():
                key = str(term)
                weighted_scores[key] = weighted_scores.get(key, 0.0) + float(strength) * weight

        strongest_score = max([weighted_scores.get(term, 0.0) for term in terms] or [0.0])
        if strongest_score <= 0:
            return {}
        return {
            term: round(weighted_scores.get(term, 0.0) / strongest_score, 4)
            for term in terms
            if weighted_scores.get(term, 0.0) > 0
        }

    @staticmethod
    def _compose_group_aliases(*alias_maps: dict[str, str]) -> dict[str, str]:
        combined: dict[str, str] = {}
        for alias_map in alias_maps:
            for source, target in alias_map.items():
                combined[str(source)] = str(target)

        def resolve(group_id: str) -> str:
            seen: set[str] = set()
            current = str(group_id)
            while current in combined and current not in seen:
                seen.add(current)
                next_group_id = combined[current]
                if next_group_id == current:
                    break
                current = next_group_id
            return current

        return {source: resolve(target) for source, target in combined.items()}

    def _group_by_matching_labels(self, groups: list[AnalysisGroupRecord]) -> list[list[AnalysisGroupRecord]]:
        parents = list(range(len(groups)))

        def find(index: int) -> int:
            while parents[index] != index:
                parents[index] = parents[parents[index]]
                index = parents[index]
            return index

        def union(left: int, right: int) -> None:
            left_root = find(left)
            right_root = find(right)
            if left_root != right_root:
                parents[right_root] = left_root

        exact_label_indexes: dict[tuple[bool, str], int] = {}
        ngram_indexes: dict[tuple[bool, str], int] = {}
        for index, group in enumerate(groups):
            is_noise = bool(group.is_noise)
            normalized_label = self._normalize_group_label(group.label)
            exact_label = normalized_label or str(group.group_id).strip()
            exact_key = (is_noise, exact_label)
            if exact_key in exact_label_indexes:
                union(exact_label_indexes[exact_key], index)
            else:
                exact_label_indexes[exact_key] = index

            for label_ngram in self._label_merge_ngrams(normalized_label):
                ngram_key = (is_noise, label_ngram)
                if ngram_key in ngram_indexes:
                    union(ngram_indexes[ngram_key], index)
                else:
                    ngram_indexes[ngram_key] = index

        grouped: dict[int, list[AnalysisGroupRecord]] = {}
        for index, group in enumerate(groups):
            grouped.setdefault(find(index), []).append(group)
        return list(grouped.values())

    @classmethod
    def _label_merge_ngrams(cls, label: str) -> set[str]:
        tokens = cls._label_merge_tokens(label)
        ngrams: set[str] = set()
        for ngram_size in (2, 3):
            for index in range(0, len(tokens) - ngram_size + 1):
                ngrams.add(" ".join(tokens[index:index + ngram_size]))
        return ngrams

    @staticmethod
    def _label_merge_tokens(label: str) -> list[str]:
        stopwords = set(DocumentRelevanceSorter.STOPWORDS) - {"too"}
        return [
            token.casefold()
            for token in DocumentRelevanceSorter.TOKEN_PATTERN.findall(str(label or ""))
            if len(token) > 2 and token.casefold() not in stopwords
        ]

    def _move_off_topic_documents_to_noise(
        self,
        groups: list[AnalysisGroupRecord],
    ) -> tuple[list[AnalysisGroupRecord], set[int], int]:
        if not groups:
            return [], set(), 0

        moved_documents_by_row: dict[int, AnalysisDocumentRecord] = {}
        for group in list(groups):
            if group.is_noise:
                continue
            documents = list(group.documents)
            if len(documents) < 2:
                continue

            keep_documents: list[AnalysisDocumentRecord] = []
            for document in documents:
                row_number = int(document.row_number)
                overlap_count = DocumentRelevanceSorter.overlap_count(
                    document.text,
                    label=group.label,
                    terms=group.terms,
                )
                if overlap_count > 0:
                    keep_documents.append(document)
                    continue
                if row_number > 0:
                    moved_documents_by_row[row_number] = document

            group.documents = keep_documents
            keep_row_numbers = {int(document.row_number) for document in keep_documents}
            group.examples = [example for example in group.examples if int(example.row_number) in keep_row_numbers]
            self._backfill_examples_from_documents(group)

        if not moved_documents_by_row:
            return self._drop_empty_non_noise_groups(groups), set(), 0

        noise_group = self._find_or_create_noise_group(groups)
        moved_documents = sorted(moved_documents_by_row.values(), key=lambda document: int(document.row_number))
        existing_noise_rows = {int(document.row_number) for document in noise_group.documents}
        for document in moved_documents:
            if int(document.row_number) not in existing_noise_rows:
                noise_group.documents.append(document)
        noise_group.documents = sorted(noise_group.documents, key=lambda document: int(document.row_number))
        self._backfill_examples_from_documents(noise_group)

        rebuilt_groups = self._drop_empty_non_noise_groups(groups)
        self._refresh_group_counts(rebuilt_groups)
        return rebuilt_groups, set(moved_documents_by_row), len(moved_documents_by_row)

    def _find_or_create_noise_group(self, groups: list[AnalysisGroupRecord]) -> AnalysisGroupRecord:
        for group in groups:
            if group.is_noise or str(group.group_id) == "-1":
                group.is_noise = True
                group.group_id = "-1"
                group.label = "Unassigned responses"
                return group

        noise_group = AnalysisGroupRecord(
            group_id="-1",
            label="Unassigned responses",
            is_noise=True,
            count=0,
            share=0.0,
            total_documents=0,
            terms=[],
            examples=[],
            documents=[],
        )
        groups.append(noise_group)
        return noise_group

    def _backfill_examples_from_documents(self, group: AnalysisGroupRecord) -> None:
        if len(group.examples) >= self.config.representative_examples_per_group:
            group.examples = group.examples[: self.config.representative_examples_per_group]
            return

        existing_rows = {int(example.row_number) for example in group.examples}
        for document in group.documents:
            row_number = int(document.row_number)
            if row_number in existing_rows:
                continue
            group.examples.append(
                AnalysisExampleRecord(
                    row_number=row_number,
                    text=document.text,
                )
            )
            existing_rows.add(row_number)
            if len(group.examples) >= self.config.representative_examples_per_group:
                break

    @staticmethod
    def _drop_empty_non_noise_groups(groups: list[AnalysisGroupRecord]) -> list[AnalysisGroupRecord]:
        return [
            group
            for group in groups
            if group.is_noise or group.documents
        ]

    def _refresh_group_counts(self, groups: list[AnalysisGroupRecord]) -> None:
        total_documents = max(1, sum(len(group.documents) for group in groups))
        for group in groups:
            group.count = len(group.documents)
            group.share = round(group.count / total_documents, 4)
            group.total_documents = total_documents
        groups.sort(key=lambda group: (bool(group.is_noise), -int(group.count), str(group.group_id)))

    def _refresh_group_comments(self, groups: list[AnalysisGroupRecord]) -> None:
        for group in groups:
            group.comment = self.output_translation_service.narrative_service.build_comment(
                label=group.label or "Group",
                count=int(group.count or len(group.documents)),
                total_documents=max(1, int(group.total_documents or group.count or len(group.documents))),
                examples=list(group.examples),
            )

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
        return max(0.6, min(1.0, float(value)))
