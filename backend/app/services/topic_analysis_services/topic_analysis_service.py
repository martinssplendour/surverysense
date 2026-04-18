"""Orchestrates the full topic-analysis pipeline: validation, text prep, embeddings, clustering, labelling, and translation."""
from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, cast

import pandas as pd

from app.core.exceptions import TopicAnalysisError, TopicAnalysisInputError
from app.services.topic_analysis_services.bertopic_service import BertopicAnalysisService
from app.services.topic_analysis_services.config import (
    PreparedDocument,
    PreparedTextDataset,
    TopicAnalysisConfig,
)
from app.services.topic_analysis_services.embedding_service import SentenceEmbeddingService
from app.services.topic_analysis_services.example_selection_service import RepresentativeExampleSelectionService
from app.services.topic_analysis_services.group_assembly_service import (
    TopicGroupAssemblyService,
)
from app.services.topic_analysis_services.hdbscan_service import HdbscanAnalysisService
from app.services.topic_analysis_services.keyword_service import TopicAnalysisKeywordService
from app.services.topic_analysis_services.kmeans_service import KMeansAnalysisService
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
from app.services.topic_label_ai_service import TopicAiLabelService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _PreparedAnalysisRun:
    prepared: PreparedTextDataset
    base_response: dict[str, object]
    warnings: list[str]


@dataclass(slots=True)
class _ModelExecution:
    model_result: dict[str, object]
    embeddings: Any
    scatter_embeddings: Any | None = None


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
        ai_label_service: TopicAiLabelService | None = None,
    ) -> None:
        self.config = config
        self.input_validation_service = input_validation_service
        self.text_preparation_service = text_preparation_service
        self.keyword_service = keyword_service
        self.narrative_service = narrative_service
        self.representative_example_service = representative_example_service
        self.embedding_service = embedding_service
        self.ngram_service = ngram_service
        self.kmeans_service = kmeans_service
        self.hdbscan_service = hdbscan_service
        self.bertopic_service = bertopic_service
        self.ai_label_service = ai_label_service
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
        self.embedding_service.warm_up(
            model_name=self.config.embedding_model,
            local_model_path=self.config.embedding_local_path,
        )
        try:
            import numpy as _np
            import umap as _umap

            dummy_embeddings = _np.random.default_rng(0).random((50, 50))
            _umap.UMAP(n_neighbors=10, n_components=5, random_state=42).fit_transform(dummy_embeddings)
        except Exception:
            pass

    def run(
        self,
        *,
        result_id: str,
        dataframe: pd.DataFrame,
        model_key: str,
        text_column_name: str,
        available_verbatim_columns: Iterable[str],
    ) -> dict[str, object]:
        base_response = self._build_base_response(
            result_id=result_id,
            model_key=model_key,
            text_column_name=text_column_name,
            filtered_row_count=int(len(dataframe)),
        )

        try:
            prepared_run = self._prepare_run(
                base_response=base_response,
                dataframe=dataframe,
                model_key=model_key,
                text_column_name=text_column_name,
                available_verbatim_columns=available_verbatim_columns,
            )
            if model_key == "ngrams":
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
                    model_key,
                    text_column_name,
                    exc,
                )
            else:
                logger.warning(
                    "Topic analysis failed for result_id=%s model=%s column=%s (%s: %s).",
                    result_id,
                    model_key,
                    text_column_name,
                    type(exc).__name__,
                    exc,
                )
            return self._build_error_response(base_response, str(exc))
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.exception(
                "Topic analysis crashed unexpectedly for result_id=%s model=%s column=%s.",
                result_id,
                model_key,
                text_column_name,
            )
            return self._build_error_response(base_response, f"Analysis failed unexpectedly: {exc}")

    def _prepare_run(
        self,
        *,
        base_response: dict[str, object],
        dataframe: pd.DataFrame,
        model_key: str,
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
        base_response["valid_document_count"] = int(len(prepared.documents))
        base_response["skipped_document_count"] = int(prepared.skipped_row_count)
        base_response["warnings"] = warnings
        return _PreparedAnalysisRun(
            prepared=prepared,
            base_response=base_response,
            warnings=warnings,
        )

    def _run_ngram_analysis(self, prepared_run: _PreparedAnalysisRun) -> dict[str, object]:
        ngram_buckets = self.ngram_service.run(
            prepared_run.prepared.documents,
            top_n=self.config.top_ngrams_per_bucket,
        )
        translated_bucket_count, translation_warnings = self._translate_ngram_buckets(ngram_buckets)
        prepared_run.warnings.extend(translation_warnings)
        prepared_run.base_response["warnings"] = prepared_run.warnings
        prepared_run.base_response["ok"] = True
        prepared_run.base_response["translated_document_count"] = translated_bucket_count
        prepared_run.base_response["ngram_buckets"] = ngram_buckets
        return prepared_run.base_response

    def _run_grouped_analysis(
        self,
        *,
        prepared_run: _PreparedAnalysisRun,
        model_key: str,
        text_column_name: str,
    ) -> dict[str, object]:
        execution = self._execute_model(
            model_key=model_key,
            texts=list(prepared_run.prepared.texts),
        )
        prepared_run.warnings.extend(self._coerce_warnings(execution.model_result))
        groups = self._build_groups(
            documents=prepared_run.prepared.documents,
            assignments=self._coerce_assignments(execution.model_result),
            explicit_groups=self._coerce_explicit_groups(execution.model_result),
            model_key=model_key,
        )
        _, ai_warnings = self._apply_ai_labels(
            groups,
            model_key=model_key,
            text_column_name=text_column_name,
        )
        prepared_run.warnings.extend(ai_warnings)
        translated_group_count, translation_warnings = self._translate_group_outputs(groups)
        prepared_run.warnings.extend(translation_warnings)

        prepared_run.base_response["warnings"] = prepared_run.warnings
        prepared_run.base_response["translated_document_count"] = translated_group_count
        prepared_run.base_response["groups"] = groups
        prepared_run.base_response["ok"] = True

        if model_key == "kmeans" and execution.scatter_embeddings is not None:
            prepared_run.base_response["scatter_points"] = self._build_scatter_points(
                documents=prepared_run.prepared.documents,
                assignments=self._coerce_assignments(execution.model_result),
                embeddings=execution.scatter_embeddings,
                groups=groups,
            )

        return prepared_run.base_response

    def _execute_model(self, *, model_key: str, texts: list[str]) -> _ModelExecution:
        embeddings = self.embedding_service.encode(
            texts,
            model_name=self.config.embedding_model,
            local_model_path=self.config.embedding_local_path,
        )
        if model_key == "bertopic":
            return _ModelExecution(
                model_result=self.bertopic_service.run(
                    texts,
                    embeddings,
                    top_terms=self.config.top_terms_per_group,
                    language=self.config.bertopic_language,
                    reduce_outliers=self.config.bertopic_reduce_outliers,
                    outlier_threshold=self.config.bertopic_outlier_threshold,
                ),
                embeddings=embeddings,
            )
        if model_key == "kmeans":
            scatter_embeddings = self._reduce_kmeans_embeddings(embeddings)
            return _ModelExecution(
                model_result=self.kmeans_service.run(
                    scatter_embeddings,
                    requested_clusters=self.config.kmeans_clusters,
                    random_state=self.config.kmeans_random_state,
                ),
                embeddings=embeddings,
                scatter_embeddings=scatter_embeddings,
            )
        if model_key == "hdbscan":
            return _ModelExecution(
                model_result=self.hdbscan_service.run(
                    embeddings,
                    min_cluster_size=self.config.hdbscan_min_cluster_size,
                    min_samples=self.config.hdbscan_min_samples,
                    metric=self.config.hdbscan_metric,
                ),
                embeddings=embeddings,
            )
        raise TopicAnalysisInputError(f"Unsupported analysis mode '{model_key}'.")

    @staticmethod
    def _reduce_kmeans_embeddings(embeddings: Any) -> Any:
        try:
            import numpy as np
            from sklearn.decomposition import PCA
        except ImportError:
            return embeddings

        embedding_array = np.asarray(embeddings)
        if (
            embedding_array.ndim != 2
            or embedding_array.shape[0] < 10
            or embedding_array.shape[1] <= 50
        ):
            return embeddings

        n_pca = min(50, embedding_array.shape[1], embedding_array.shape[0] - 1)
        if n_pca < 2:
            return embeddings
        return PCA(n_components=n_pca, random_state=42).fit_transform(embedding_array)

    @staticmethod
    def _coerce_assignments(model_result: dict[str, object]) -> list[int]:
        raw_assignments = model_result.get("assignments", [])
        if not isinstance(raw_assignments, list):
            return []

        assignments: list[int] = []
        for value in raw_assignments:
            if isinstance(value, (int, float, str)):
                assignments.append(int(value))
        return assignments

    @staticmethod
    def _coerce_warnings(model_result: dict[str, object]) -> list[str]:
        raw_warnings = model_result.get("warnings", [])
        if not isinstance(raw_warnings, list):
            return []
        return [warning for warning in raw_warnings if isinstance(warning, str)]

    @staticmethod
    def _coerce_explicit_groups(model_result: dict[str, object]) -> dict[str, dict[str, object]]:
        raw_groups = model_result.get("groups", {})
        if not isinstance(raw_groups, dict):
            return {}

        explicit_groups: dict[str, dict[str, object]] = {}
        for key, value in raw_groups.items():
            if isinstance(key, str) and isinstance(value, dict):
                explicit_groups[key] = cast(dict[str, object], value)
        return explicit_groups

    def _build_base_response(
        self,
        *,
        result_id: str,
        model_key: str,
        text_column_name: str,
        filtered_row_count: int,
    ) -> dict[str, object]:
        return {
            "ok": False,
            "result_id": result_id,
            "model_key": model_key,
            "model_label": self.input_validation_service.get_model_label(model_key),
            "text_column_name": text_column_name,
            "filtered_row_count": filtered_row_count,
            "valid_document_count": 0,
            "skipped_document_count": 0,
            "translated_document_count": 0,
            "warnings": [],
            "error": None,
            "groups": [],
            "ngram_buckets": [],
            "scatter_points": [],
        }

    @staticmethod
    def _build_error_response(base_response: dict[str, object], message: str) -> dict[str, object]:
        failed_response = dict(base_response)
        failed_response["error"] = message
        return failed_response

    def _build_groups(
        self,
        *,
        documents: list[PreparedDocument],
        assignments: list[int],
        explicit_groups: dict[str, dict[str, object]],
        model_key: str,
    ) -> list[dict[str, object]]:
        return cast(
            list[dict[str, object]],
            self.group_assembly_service.build_groups(
                documents=documents,
                assignments=assignments,
                explicit_groups=explicit_groups,
                model_key=model_key,
            ),
        )

    def _translate_and_merge_bertopic_groups(
        self, groups: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        return cast(
            list[dict[str, object]],
            self.group_assembly_service.translate_and_merge_bertopic_groups(groups),
        )

    @staticmethod
    def _sample_group_texts(grouped_texts: list[str], *, limit: int) -> list[str]:
        return cast(
            list[str],
            TopicAnalysisOutputTranslationService.sample_group_texts(grouped_texts, limit=limit),
        )

    def _apply_ai_labels(
        self,
        groups: list[dict[str, object]],
        *,
        model_key: str,
        text_column_name: str,
    ) -> tuple[int, list[str]]:
        return cast(
            tuple[int, list[str]],
            self.output_translation_service.apply_ai_labels(
                groups,
                model_key=model_key,
                text_column_name=text_column_name,
            ),
        )

    def _translate_group_outputs(self, groups: list[dict[str, object]]) -> tuple[int, list[str]]:
        return cast(tuple[int, list[str]], self.output_translation_service.translate_group_outputs(groups))

    def _translate_ngram_buckets(self, buckets: list[dict[str, object]]) -> tuple[int, list[str]]:
        return cast(tuple[int, list[str]], self.output_translation_service.translate_ngram_buckets(buckets))

    def _build_scatter_points(
        self,
        *,
        documents: list[PreparedDocument],
        assignments: list[int],
        embeddings: Any,
        groups: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        return cast(
            list[dict[str, object]],
            self.scatter_projection_service.build_scatter_points(
                documents=documents,
                assignments=assignments,
                embeddings=embeddings,
                groups=groups,
            ),
        )
