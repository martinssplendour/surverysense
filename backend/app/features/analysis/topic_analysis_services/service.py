"""Orchestrates the full topic-analysis pipeline: validation, text prep, community detection, labelling, and translation."""
from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, replace

import pandas as pd

from app.core.exceptions import TopicAnalysisError, TopicAnalysisInputError, TopicAnalysisRateLimitError
from app.features.analysis.topic_analysis_services.community_detection_service import (
    CommunityDetectionAnalysisService,
)
from app.features.analysis.topic_analysis_services.config import (
    PreparedTextDataset,
    TopicAnalysisConfig,
)
from app.features.analysis.topic_analysis_services.contracts import (
    AnalysisRunResult,
)
from app.features.analysis.topic_analysis_services.community_plot_records import CommunityPlotRecordBuilder
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
from app.features.analysis.topic_analysis_services.group_post_processing_service import (
    TopicGroupPostProcessingService,
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
        self.group_post_processor = TopicGroupPostProcessingService(
            config=config,
            narrative_service=narrative_service,
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
        groups, top_term_aliases = self.group_post_processor.merge_groups_by_top_term_signature(groups)
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
        groups, label_aliases = self.group_post_processor.merge_duplicate_label_groups(groups)
        group_id_aliases = self.group_post_processor.compose_group_aliases(top_term_aliases, label_aliases)
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
        groups, weak_noise_row_numbers, weak_noise_count = self.group_post_processor.move_off_topic_documents_to_noise(groups)
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
        self.group_post_processor.refresh_group_comments(groups)
        scatter_points, network_edges = CommunityPlotRecordBuilder.build(
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

    def _normalize_community_similarity_threshold(self, value: float | None) -> float:
        if value is None:
            return float(self.config.community_similarity_threshold)
        return max(0.6, min(1.0, float(value)))
