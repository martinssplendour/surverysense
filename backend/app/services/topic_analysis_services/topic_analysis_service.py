"""Orchestrates the full topic-analysis pipeline: validation, text prep, clustering, labelling, and translation."""
from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, replace

import pandas as pd

from app.core.exceptions import TopicAnalysisError, TopicAnalysisInputError
from app.models.enums import AnalysisModelKey
from app.services.service_protocols import TopicLabelServiceProtocol
from app.services.topic_analysis_services.bertopic_service import BertopicAnalysisService
from app.services.topic_analysis_services.config import (
    PreparedTextDataset,
    TopicAnalysisConfig,
)
from app.services.topic_analysis_services.contracts import AnalysisRunResult
from app.services.topic_analysis_services.embedding_service import SentenceEmbeddingService
from app.services.topic_analysis_services.example_selection_service import RepresentativeExampleSelectionService
from app.services.topic_analysis_services.group_assembly_service import (
    TopicGroupAssemblyService,
)
from app.services.topic_analysis_services.hdbscan_service import HdbscanAnalysisService
from app.services.topic_analysis_services.keyword_service import TopicAnalysisKeywordService
from app.services.topic_analysis_services.kmeans_service import KMeansAnalysisService
from app.services.topic_analysis_services.model_execution_service import (
    TopicModelExecutionService,
)
from app.services.topic_analysis_services.narrative_service import TopicAnalysisNarrativeService
from app.services.topic_analysis_services.ngram_service import NgramAnalysisService
from app.services.topic_analysis_services.output_translation_service import (
    TopicAnalysisOutputTranslationService,
)
from app.services.topic_analysis_services.scatter_projection_service import (
    TopicScatterProjectionService,
)
from app.services.topic_analysis_services.text_preparation_service import TopicAnalysisTextPreparationService
from app.services.topic_analysis_services.validation_service import TopicAnalysisInputValidationService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _PreparedAnalysisRun:
    prepared: PreparedTextDataset
    result: AnalysisRunResult


class TopicAnalysisService:
    """End-to-end topic analysis service that routes to the appropriate model (BERTopic, K-means, HDBSCAN, n-grams)."""

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
        kmeans_service: KMeansAnalysisService,
        hdbscan_service: HdbscanAnalysisService,
        bertopic_service: BertopicAnalysisService,
        ai_label_service: TopicLabelServiceProtocol | None = None,
    ) -> None:
        self.config = config
        self.input_validation_service = input_validation_service
        self.text_preparation_service = text_preparation_service
        self.ngram_service = ngram_service
        self.model_execution_service = TopicModelExecutionService(
            config=config,
            embedding_service=embedding_service,
            kmeans_service=kmeans_service,
            hdbscan_service=hdbscan_service,
            bertopic_service=bertopic_service,
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
        self.scatter_projection_service = TopicScatterProjectionService(
            random_state=config.kmeans_random_state,
        )

    def warm_up(self) -> None:
        self.text_preparation_service.warm_up()
        self.model_execution_service.warm_up()

    def run(
        self,
        *,
        result_id: str,
        dataframe: pd.DataFrame,
        model_key: AnalysisModelKey,
        text_column_name: str,
        available_verbatim_columns: Iterable[str],
    ) -> AnalysisRunResult:
        base_result = AnalysisRunResult.empty(
            result_id=result_id,
            model_key=model_key,
            text_column_name=text_column_name,
            filtered_row_count=int(len(dataframe)),
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
            translated_document_count=translated_bucket_count,
            warnings=warnings,
            ngram_buckets=ngram_buckets,
        )

    def _run_grouped_analysis(
        self,
        *,
        prepared_run: _PreparedAnalysisRun,
        model_key: AnalysisModelKey,
        text_column_name: str,
    ) -> AnalysisRunResult:
        execution = self.model_execution_service.execute(
            model_key=model_key,
            texts=list(prepared_run.prepared.texts),
        )
        warnings = list(prepared_run.result.warnings)
        warnings.extend(execution.result.warnings)

        groups = self.group_assembly_service.build_groups(
            documents=prepared_run.prepared.documents,
            assignments=execution.result.assignments,
            explicit_groups=execution.result.groups,
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

        scatter_points = []
        if model_key == AnalysisModelKey.KMEANS and execution.scatter_embeddings is not None:
            scatter_points = self.scatter_projection_service.build_scatter_points(
                documents=prepared_run.prepared.documents,
                assignments=execution.result.assignments,
                embeddings=execution.scatter_embeddings,
                groups=groups,
            )

        return replace(
            prepared_run.result,
            ok=True,
            translated_document_count=translated_group_count,
            warnings=warnings,
            groups=groups,
            scatter_points=scatter_points,
        )

    @staticmethod
    def _build_error_response(base_result: AnalysisRunResult, message: str) -> AnalysisRunResult:
        return replace(base_result, error=message)
