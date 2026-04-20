from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.enums import AnalysisModelKey
from app.services.topic_analysis_services.bertopic_service import BertopicAnalysisService
from app.services.topic_analysis_services.config import TopicAnalysisConfig
from app.services.topic_analysis_services.contracts import TopicModelRunResult
from app.services.topic_analysis_services.embedding_service import SentenceEmbeddingService
from app.services.topic_analysis_services.hdbscan_service import HdbscanAnalysisService
from app.services.topic_analysis_services.kmeans_service import KMeansAnalysisService


@dataclass(slots=True)
class TopicModelExecution:
    result: TopicModelRunResult
    embeddings: Any
    scatter_embeddings: Any | None = None


class TopicModelExecutionService:
    def __init__(
        self,
        *,
        config: TopicAnalysisConfig,
        embedding_service: SentenceEmbeddingService,
        kmeans_service: KMeansAnalysisService,
        hdbscan_service: HdbscanAnalysisService,
        bertopic_service: BertopicAnalysisService,
    ) -> None:
        self.config = config
        self.embedding_service = embedding_service
        self.kmeans_service = kmeans_service
        self.hdbscan_service = hdbscan_service
        self.bertopic_service = bertopic_service

    def warm_up(self) -> None:
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

    def execute(self, *, model_key: AnalysisModelKey, texts: list[str]) -> TopicModelExecution:
        embeddings = self.embedding_service.encode(
            texts,
            model_name=self.config.embedding_model,
            local_model_path=self.config.embedding_local_path,
        )
        if model_key == AnalysisModelKey.BERTOPIC:
            return TopicModelExecution(
                result=self.bertopic_service.run(
                    texts,
                    embeddings,
                    top_terms=self.config.top_terms_per_group,
                    language=self.config.bertopic_language,
                    reduce_outliers=self.config.bertopic_reduce_outliers,
                    outlier_threshold=self.config.bertopic_outlier_threshold,
                ),
                embeddings=embeddings,
            )
        if model_key == AnalysisModelKey.KMEANS:
            scatter_embeddings = self._reduce_kmeans_embeddings(embeddings)
            return TopicModelExecution(
                result=self.kmeans_service.run(
                    scatter_embeddings,
                    requested_clusters=self.config.kmeans_clusters,
                    random_state=self.config.kmeans_random_state,
                ),
                embeddings=embeddings,
                scatter_embeddings=scatter_embeddings,
            )
        if model_key == AnalysisModelKey.HDBSCAN:
            return TopicModelExecution(
                result=self.hdbscan_service.run(
                    embeddings,
                    min_cluster_size=self.config.hdbscan_min_cluster_size,
                    min_samples=self.config.hdbscan_min_samples,
                    metric=self.config.hdbscan_metric,
                ),
                embeddings=embeddings,
            )
        raise ValueError(f"Unsupported analysis mode '{model_key.value}'.")

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
