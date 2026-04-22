from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.exceptions import TopicAnalysisDependencyError
from app.models.enums import AnalysisModelKey
from app.services.topic_analysis_services.community_detection_service import (
    CommunityDetectionAnalysisService,
)
from app.services.topic_analysis_services.config import TopicAnalysisConfig
from app.services.topic_analysis_services.contracts import TopicModelRunResult
from app.services.topic_analysis_services.embedding_service import SentenceEmbeddingService


@dataclass(slots=True)
class TopicModelExecution:
    result: TopicModelRunResult
    embeddings: Any
    warnings: list[str] | None = None


class TopicModelExecutionService:
    def __init__(
        self,
        *,
        config: TopicAnalysisConfig,
        embedding_service: SentenceEmbeddingService,
        community_detection_service: CommunityDetectionAnalysisService,
    ) -> None:
        self.config = config
        self.embedding_service = embedding_service
        self.community_detection_service = community_detection_service

    def warm_up(self) -> None:
        self.embedding_service.warm_up(
            provider=self.config.embedding_provider,
            model_name=self.config.embedding_model,
        )

    def execute(self, *, model_key: AnalysisModelKey, texts: list[str]) -> TopicModelExecution:
        if model_key != AnalysisModelKey.COMMUNITY:
            raise ValueError(f"Unsupported analysis mode '{model_key.value}'.")

        embeddings, embedding_warnings = self._encode_texts(texts)
        return TopicModelExecution(
            result=self.community_detection_service.run(
                embeddings,
                similarity_threshold=self.config.community_similarity_threshold,
                max_neighbors=self.config.community_max_neighbors,
                resolution=self.config.community_resolution,
                mutual_neighbors=self.config.community_mutual_neighbors,
            ),
            embeddings=embeddings,
            warnings=embedding_warnings,
        )

    def _encode_texts(self, texts: list[str]) -> tuple[Any, list[str]]:
        try:
            embeddings = self.embedding_service.encode(
                texts,
                provider=self.config.embedding_provider,
                model_name=self.config.embedding_model,
                api_key=self.config.embedding_api_key,
                dimensions=self.config.embedding_dimensions,
                batch_size=self.config.embedding_batch_size,
                timeout_seconds=self.config.embedding_timeout_seconds,
            )
            return embeddings, []
        except TopicAnalysisDependencyError as primary_error:
            if not self._has_embedding_fallback():
                raise

            try:
                embeddings = self.embedding_service.encode(
                    texts,
                    provider=self.config.embedding_fallback_provider,
                    model_name=self.config.embedding_fallback_model,
                    api_key=self.config.embedding_fallback_api_key,
                    dimensions=self.config.embedding_dimensions,
                    batch_size=self.config.embedding_batch_size,
                    timeout_seconds=self.config.embedding_timeout_seconds,
                )
            except TopicAnalysisDependencyError as fallback_error:
                raise TopicAnalysisDependencyError(
                    f"{primary_error} Fallback embeddings also failed: {fallback_error}"
                ) from fallback_error

            return embeddings, [
                (
                    f"{self._display_provider(self.config.embedding_provider)} embeddings failed, "
                    f"so {self._display_provider(self.config.embedding_fallback_provider)} embeddings were used for this run."
                )
            ]

    def _has_embedding_fallback(self) -> bool:
        provider = (self.config.embedding_fallback_provider or "").strip().casefold()
        if not provider:
            return False
        if provider == (self.config.embedding_provider or "").strip().casefold():
            return False
        return bool(self.config.embedding_fallback_model and self.config.embedding_fallback_api_key)

    @staticmethod
    def _display_provider(provider: str) -> str:
        normalized = (provider or "").strip().casefold()
        if normalized == "openai":
            return "OpenAI"
        if normalized == "gemini":
            return "Gemini"
        return normalized or "Fallback"
