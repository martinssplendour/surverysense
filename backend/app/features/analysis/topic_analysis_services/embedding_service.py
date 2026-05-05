"""Embeds text through hosted Gemini or OpenAI embedding providers."""
from __future__ import annotations

from collections import OrderedDict
from threading import Lock
from time import monotonic
from typing import Any
from collections.abc import Callable

from app.core.exceptions import TopicAnalysisDependencyError
from app.features.analysis.topic_analysis_services.embedding_cache import EmbeddingCacheMixin
from app.features.analysis.topic_analysis_services.embedding_provider_errors import EmbeddingProviderErrorMixin


class SentenceEmbeddingService(EmbeddingCacheMixin, EmbeddingProviderErrorMixin):
    """Provider adapter for topic-analysis embeddings with retries and in-memory caching."""

    GEMINI_MAX_BATCH_SIZE = 100
    GEMINI_RATE_LIMIT_RETRY_SECONDS = 60
    GEMINI_RATE_LIMIT_ERROR_CODE = "gemini_rate_limited"
    RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})

    def __init__(
        self,
        *,
        cache_size: int = 512,
        cache_ttl_seconds: int = 900,
        max_retries: int = 1,
        retry_base_seconds: float = 0.75,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.cache_size = max(0, int(cache_size or 0))
        self.cache_ttl_seconds = max(0, int(cache_ttl_seconds or 0))
        self.max_retries = max(0, int(max_retries or 0))
        self.retry_base_seconds = max(0.0, float(retry_base_seconds or 0.0))
        self._clock = clock
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._cache_saved_at: dict[str, float] = {}
        self._cache_lock = Lock()

    @staticmethod
    def _coerce_batch_size(batch_size: int) -> int:
        return max(1, int(batch_size or 1))

    @classmethod
    def _coerce_gemini_batch_size(cls, batch_size: int) -> int:
        return min(cls.GEMINI_MAX_BATCH_SIZE, cls._coerce_batch_size(batch_size))

    @staticmethod
    def _normalise_embedding_array(vectors: list[list[float]]):
        try:
            import numpy as np
        except Exception as exc:  # pragma: no cover - dependency error path
            raise TopicAnalysisDependencyError(
                "numpy is required for embedding-based analysis."
            ) from exc

        embeddings = np.asarray(vectors, dtype=np.float32)
        if embeddings.ndim != 2:
            raise TopicAnalysisDependencyError("Embedding provider returned an invalid embedding shape.")

        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        return np.divide(
            embeddings,
            norms,
            out=np.zeros_like(embeddings),
            where=norms != 0,
        )

    def warm_up(
        self,
        *,
        model_name: str,
        provider: str = "gemini",
    ) -> None:
        return

    def cleanup_expired(self) -> int:
        with self._cache_lock:
            return self._purge_expired_locked()

    def encode(
        self,
        texts: list[str],
        *,
        model_name: str,
        provider: str = "gemini",
        api_key: str = "",
        dimensions: int = 0,
        batch_size: int = 128,
        timeout_seconds: int = 60,
    ):
        """Encode texts to a numpy float array of L2-normalised embeddings."""
        if not texts:
            return []

        provider = self._normalise_provider(provider)
        api_key = self._require_api_key(provider=provider, api_key=api_key)
        if self.cache_size <= 0:
            vectors = self._encode_uncached(
                texts,
                provider=provider,
                model_name=model_name,
                api_key=api_key,
                dimensions=dimensions,
                batch_size=batch_size,
                timeout_seconds=timeout_seconds,
            )
            return self._normalise_embedding_array(vectors)

        return self._encode_with_cache(
            texts,
            provider=provider,
            model_name=model_name,
            api_key=api_key,
            dimensions=dimensions,
            batch_size=batch_size,
            timeout_seconds=timeout_seconds,
        )

    def _encode_with_cache(
        self,
        texts: list[str],
        *,
        provider: str,
        model_name: str,
        api_key: str,
        dimensions: int,
        batch_size: int,
        timeout_seconds: int,
    ):
        cache_keys = [
            self._cache_key(
                provider=provider,
                model_name=model_name,
                dimensions=dimensions,
                text=text,
            )
            for text in texts
        ]
        vectors: list[Any | None] = [None] * len(texts)
        missing: OrderedDict[str, str] = OrderedDict()

        with self._cache_lock:
            self._purge_expired_locked()
            for index, (key, text) in enumerate(zip(cache_keys, texts)):
                cached_vector = self._cache.get(key)
                if cached_vector is None:
                    missing.setdefault(key, text)
                    continue
                self._cache.move_to_end(key)
                vectors[index] = cached_vector.copy()

        if missing:
            fetched_vectors = self._encode_uncached(
                list(missing.values()),
                provider=provider,
                model_name=model_name,
                api_key=api_key,
                dimensions=dimensions,
                batch_size=batch_size,
                timeout_seconds=timeout_seconds,
            )
            if len(fetched_vectors) != len(missing):
                raise TopicAnalysisDependencyError(
                    f"{self._display_provider(provider)} embeddings response returned an unexpected number of vectors."
                )
            fetched_by_key = dict(zip(missing.keys(), fetched_vectors))
            self._store_cached_vectors(fetched_by_key)
            for index, key in enumerate(cache_keys):
                if vectors[index] is None:
                    vectors[index] = fetched_by_key[key]

        return self._normalise_embedding_array([vector if vector is not None else [] for vector in vectors])

    def _encode_uncached(
        self,
        texts: list[str],
        *,
        provider: str,
        model_name: str,
        api_key: str,
        dimensions: int,
        batch_size: int,
        timeout_seconds: int,
    ) -> list[list[float]]:
        if provider == "gemini":
            return self._encode_gemini_uncached(
                texts,
                model_name=model_name,
                api_key=api_key,
                dimensions=dimensions,
                batch_size=batch_size,
                timeout_seconds=timeout_seconds,
            )
        if provider == "openai":
            return self._encode_openai_uncached(
                texts,
                model_name=model_name,
                api_key=api_key,
                dimensions=dimensions,
                batch_size=batch_size,
                timeout_seconds=timeout_seconds,
            )
        raise TopicAnalysisDependencyError(
            "Unsupported TOPIC_EMBEDDING_PROVIDER. Use 'gemini' or 'openai'."
        )

    def _encode_openai_uncached(
        self,
        texts: list[str],
        *,
        model_name: str,
        api_key: str,
        dimensions: int,
        batch_size: int,
        timeout_seconds: int,
    ) -> list[list[float]]:
        try:
            import requests
        except Exception as exc:  # pragma: no cover - dependency error path
            raise TopicAnalysisDependencyError(
                "requests is required for OpenAI embedding-based analysis."
            ) from exc

        vectors: list[list[float]] = []
        for batch in self._iter_batches(texts, self._coerce_batch_size(batch_size)):
            payload: dict[str, object] = {
                "model": model_name,
                "input": batch,
                "encoding_format": "float",
            }
            if dimensions > 0:
                payload["dimensions"] = dimensions

            response = self._post_json_with_retries(
                requests_module=requests,
                provider="openai",
                url="https://api.openai.com/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                payload=payload,
                timeout_seconds=timeout_seconds,
            )

            if response.status_code >= 400:
                self._raise_http_error(provider="openai", response=response)

            try:
                payload_json = response.json()
                items = sorted(payload_json["data"], key=lambda item: item["index"])
                vectors.extend([item["embedding"] for item in items])
            except Exception as exc:
                raise TopicAnalysisDependencyError(
                    "OpenAI embeddings response did not contain the expected embedding data."
                ) from exc

        return vectors

    def _encode_gemini_uncached(
        self,
        texts: list[str],
        *,
        model_name: str,
        api_key: str,
        dimensions: int,
        batch_size: int,
        timeout_seconds: int,
    ) -> list[list[float]]:
        try:
            import requests
        except Exception as exc:  # pragma: no cover - dependency error path
            raise TopicAnalysisDependencyError(
                "requests is required for Gemini embedding-based analysis."
            ) from exc

        model_resource = model_name if model_name.startswith("models/") else f"models/{model_name}"
        vectors: list[list[float]] = []
        for batch in self._iter_batches(texts, self._coerce_gemini_batch_size(batch_size)):
            requests_payload: list[dict[str, object]] = []
            for text in batch:
                request_payload: dict[str, object] = {
                    "model": model_resource,
                    "content": {"parts": [{"text": text}]},
                    "taskType": "CLUSTERING",
                }
                if dimensions > 0:
                    request_payload["outputDimensionality"] = dimensions
                requests_payload.append(request_payload)

            response = self._post_json_with_retries(
                requests_module=requests,
                provider="gemini",
                url=f"https://generativelanguage.googleapis.com/v1beta/{model_resource}:batchEmbedContents",
                headers={
                    "x-goog-api-key": api_key,
                    "Content-Type": "application/json",
                },
                payload={"requests": requests_payload},
                timeout_seconds=timeout_seconds,
            )

            if response.status_code >= 400:
                self._raise_http_error(provider="gemini", response=response)

            try:
                payload_json = response.json()
                vectors.extend([item["values"] for item in payload_json["embeddings"]])
            except Exception as exc:
                raise TopicAnalysisDependencyError(
                    "Gemini embeddings response did not contain the expected embedding data."
                ) from exc

        return vectors

    @staticmethod
    def _iter_batches(texts: list[str], batch_size: int):
        for index in range(0, len(texts), batch_size):
            yield texts[index:index + batch_size]

    def _purge_expired_locked(self) -> int:
        if self.cache_ttl_seconds <= 0:
            purged = len(self._cache)
            self._cache.clear()
            self._cache_saved_at.clear()
            return purged

        expires_before = self._clock() - self.cache_ttl_seconds
        expired_keys = [
            key
            for key, saved_at in self._cache_saved_at.items()
            if saved_at <= expires_before
        ]
        for key in expired_keys:
            self._cache.pop(key, None)
            self._cache_saved_at.pop(key, None)
        return len(expired_keys)
