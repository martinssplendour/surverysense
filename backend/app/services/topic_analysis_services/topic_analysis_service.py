"""Orchestrates the full topic-analysis pipeline: validation, text prep, embeddings, clustering, labelling, and translation."""
from __future__ import annotations

import logging
from typing import Iterable

import pandas as pd

from app.core.exceptions import TopicAnalysisInputError
from app.services.topic_label_ai_service import TopicAiLabelService
from app.services.topic_analysis_services.bertopic_service import BertopicAnalysisService
from app.services.topic_analysis_services.config import (
    PreparedDocument,
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


logger = logging.getLogger(__name__)


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
            _dummy = _np.random.default_rng(0).random((50, 50))
            _umap.UMAP(n_neighbors=10, n_components=5, random_state=42).fit_transform(_dummy)
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
        model_label = self.input_validation_service.get_model_label(model_key)
        base_response: dict[str, object] = {
            "ok": False,
            "result_id": result_id,
            "model_key": model_key,
            "model_label": model_label,
            "text_column_name": text_column_name,
            "filtered_row_count": int(len(dataframe)),
            "valid_document_count": 0,
            "skipped_document_count": 0,
            "translated_document_count": 0,
            "warnings": [],
            "error": None,
            "groups": [],
            "ngram_buckets": [],
            "scatter_points": [],
        }

        try:
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

            embeddings = None
            if model_key == "ngrams":
                ngram_buckets = self.ngram_service.run(
                    prepared.documents,
                    top_n=self.config.top_ngrams_per_bucket,
                )
                translated_bucket_count, translation_warnings = self._translate_ngram_buckets(ngram_buckets)
                warnings.extend(translation_warnings)
                base_response["warnings"] = warnings
                base_response["ok"] = True
                base_response["translated_document_count"] = translated_bucket_count
                base_response["ngram_buckets"] = ngram_buckets
                return base_response

            clustering_texts = list(prepared.texts)
            if model_key == "bertopic":
                embeddings = self.embedding_service.encode(
                    clustering_texts,
                    model_name=self.config.embedding_model,
                    local_model_path=self.config.embedding_local_path,
                )
                model_result = self.bertopic_service.run(
                    clustering_texts,
                    embeddings,
                    top_terms=self.config.top_terms_per_group,
                    language=self.config.bertopic_language,
                    reduce_outliers=self.config.bertopic_reduce_outliers,
                    outlier_threshold=self.config.bertopic_outlier_threshold,
                )
            else:
                embeddings = self.embedding_service.encode(
                    clustering_texts,
                    model_name=self.config.embedding_model,
                    local_model_path=self.config.embedding_local_path,
                )
                reduced_embeddings = embeddings
                if model_key == "kmeans":
                    try:
                        import numpy as np
                        from sklearn.decomposition import PCA as _PCA
                        _arr = np.asarray(embeddings)
                        if (
                            _arr.ndim == 2
                            and _arr.shape[0] >= 10
                            and _arr.shape[1] > 50
                        ):
                            _n_pca = min(50, _arr.shape[1], _arr.shape[0] - 1)
                            if _n_pca >= 2:
                                reduced_embeddings = _PCA(
                                    n_components=_n_pca, random_state=42
                                ).fit_transform(_arr)
                    except Exception:  # pragma: no cover - sklearn always present
                        pass

                if model_key == "kmeans":
                    kmeans_embeddings = reduced_embeddings
                    model_result = self.kmeans_service.run(
                        kmeans_embeddings,
                        requested_clusters=self.config.kmeans_clusters,
                        random_state=self.config.kmeans_random_state,
                    )
                elif model_key == "hdbscan":
                    model_result = self.hdbscan_service.run(
                        embeddings,
                        min_cluster_size=self.config.hdbscan_min_cluster_size,
                        min_samples=self.config.hdbscan_min_samples,
                        metric=self.config.hdbscan_metric,
                    )
                else:  # pragma: no cover - guarded by request validation
                    raise TopicAnalysisInputError(f"Unsupported analysis mode '{model_key}'.")

            warnings.extend(model_result.get("warnings", []))
            groups = self._build_groups(
                documents=prepared.documents,
                assignments=[int(value) for value in model_result.get("assignments", [])],
                explicit_groups=model_result.get("groups", {}),
                model_key=model_key,
            )
            _, ai_warnings = self._apply_ai_labels(
                groups,
                model_key=model_key,
                text_column_name=text_column_name,
            )
            warnings.extend(ai_warnings)
            translated_group_count, translation_warnings = self._translate_group_outputs(groups)
            warnings.extend(translation_warnings)
            base_response["warnings"] = warnings
            base_response["translated_document_count"] = translated_group_count
            base_response["groups"] = groups
            if model_key == "kmeans" and embeddings is not None:
                base_response["scatter_points"] = self._build_scatter_points(
                    documents=prepared.documents,
                    assignments=[int(value) for value in model_result.get("assignments", [])],
                    embeddings=kmeans_embeddings,
                    groups=groups,
                )
            base_response["ok"] = True
            return base_response
        except TopicAnalysisInputError as exc:
            base_response["error"] = str(exc)
            return base_response
        except Exception as exc:  # pragma: no cover - defensive guard
            base_response["error"] = f"Analysis failed unexpectedly: {exc}"
            return base_response

    def _build_groups(
        self,
        *,
        documents: list[PreparedDocument],
        assignments: list[int],
        explicit_groups: dict[str, dict[str, object]],
        model_key: str,
    ) -> list[dict[str, object]]:
        return self.group_assembly_service.build_groups(
            documents=documents,
            assignments=assignments,
            explicit_groups=explicit_groups,
            model_key=model_key,
        )

    def _translate_and_merge_bertopic_groups(
        self, groups: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        return self.group_assembly_service.translate_and_merge_bertopic_groups(groups)

    @staticmethod
    def _sample_group_texts(grouped_texts: list[str], *, limit: int) -> list[str]:
        return TopicAnalysisOutputTranslationService.sample_group_texts(grouped_texts, limit=limit)

    def _apply_ai_labels(
        self,
        groups: list[dict[str, object]],
        *,
        model_key: str,
        text_column_name: str,
    ) -> tuple[int, list[str]]:
        return self.output_translation_service.apply_ai_labels(
            groups,
            model_key=model_key,
            text_column_name=text_column_name,
        )

    def _translate_group_outputs(self, groups: list[dict[str, object]]) -> tuple[int, list[str]]:
        return self.output_translation_service.translate_group_outputs(groups)

    def _translate_ngram_buckets(self, buckets: list[dict[str, object]]) -> tuple[int, list[str]]:
        return self.output_translation_service.translate_ngram_buckets(buckets)

    def _build_scatter_points(
        self,
        *,
        documents: list[PreparedDocument],
        assignments: list[int],
        embeddings,
        groups: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        return self.scatter_projection_service.build_scatter_points(
            documents=documents,
            assignments=assignments,
            embeddings=embeddings,
            groups=groups,
        )
