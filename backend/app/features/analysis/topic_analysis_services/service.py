"""Orchestrates the full topic-analysis pipeline: validation, text prep, community detection, labelling, and translation."""
from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, replace

import pandas as pd

from app.core.exceptions import TopicAnalysisError, TopicAnalysisInputError
from app.models.enums import AnalysisModelKey
from app.features.common.protocols import TopicLabelServiceProtocol
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
from app.features.analysis.topic_analysis_services.example_selection_service import RepresentativeExampleSelectionService
from app.features.analysis.topic_analysis_services.group_assembly_service import (
    TopicGroupAssemblyService,
)
from app.features.analysis.topic_analysis_services.keyword_service import TopicAnalysisKeywordService
from app.features.analysis.topic_analysis_services.execution import (
    TopicModelExecutionService,
)
from app.features.analysis.topic_analysis_services.narrative_service import TopicAnalysisNarrativeService
from app.features.analysis.topic_analysis_services.ngram_service import NgramAnalysisService
from app.features.analysis.topic_analysis_services.output_translation_service import (
    TopicAnalysisOutputTranslationService,
)
from app.features.analysis.topic_analysis_services.text_preparation_service import TopicAnalysisTextPreparationService
from app.features.analysis.topic_analysis_services.validation_service import TopicAnalysisInputValidationService

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
        warnings.extend(execution.warnings or [])
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
        scatter_points, network_edges = self._build_community_plot_records(
            documents=prepared_run.prepared.documents,
            assignments=execution.result.assignments,
            groups=groups,
            layout_positions=execution.result.layout_positions,
            network_edges=execution.result.network_edges,
        )

        return replace(
            prepared_run.result,
            ok=True,
            translated_document_count=translated_group_count,
            warnings=warnings,
            groups=groups,
            scatter_points=scatter_points,
            network_edges=network_edges,
        )

    @staticmethod
    def _build_error_response(base_result: AnalysisRunResult, message: str) -> AnalysisRunResult:
        return replace(base_result, error=message)

    @staticmethod
    def _build_community_plot_records(
        *,
        documents: list[PreparedDocument],
        assignments: list[int],
        groups: list[AnalysisGroupRecord],
        layout_positions: dict[int, tuple[float, float]],
        network_edges: list[tuple[int, int, float]],
    ) -> tuple[list[AnalysisScatterPointRecord], list[AnalysisNetworkEdgeRecord]]:
        group_labels = {str(group.group_id): group.label for group in groups}
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
            group_id = str(int(assignment))
            scatter_points.append(
                AnalysisScatterPointRecord(
                    row_number=row_number,
                    text=document.text,
                    group_id=group_id,
                    group_label=group_labels.get(group_id, f"Community {group_id}"),
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
                    source_row_number=source_row_number,
                    target_row_number=target_row_number,
                    weight=float(weight),
                )
            )
        return scatter_points, edge_records
