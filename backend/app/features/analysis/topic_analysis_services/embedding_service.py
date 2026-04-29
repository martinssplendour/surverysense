"""Embeds text through hosted Gemini or OpenAI embedding providers."""
from __future__ import annotations

import hashlib
import json
import re
import time
from collections import OrderedDict
from threading import Lock
from typing import Any

from app.core.exceptions import TopicAnalysisDependencyError, TopicAnalysisRateLimitError


class SentenceEmbeddingService:
    """Provider adapter for topic-analysis embeddings with retries and in-memory caching."""

    GEMINI_MAX_BATCH_SIZE = 100
    GEMINI_RATE_LIMIT_RETRY_SECONDS = 60
    GEMINI_RATE_LIMIT_ERROR_CODE = "gemini_rate_limited"
    RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})

    def __init__(
        self,
        *,
        cache_size: int = 512,
        max_retries: int = 1,
        retry_base_seconds: float = 0.75,
    ) -> None:
        self.cache_size = max(0, int(cache_size or 0))
        self.max_retries = max(0, int(max_retries or 0))
        self.retry_base_seconds = max(0.0, float(retry_base_seconds or 0.0))
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._cache_lock = Lock()

    @staticmethod
    def _normalise_provider(provider: str) -> str:
        return (provider or "gemini").strip().casefold()

    @staticmethod
    def _display_provider(provider: str) -> str:
        normalized = SentenceEmbeddingService._normalise_provider(provider)
        if normalized == "openai":
            return "OpenAI"
        if normalized == "gemini":
            return "Gemini"
        return normalized or "Embedding provider"

    @staticmethod
    def _require_api_key(*, provider: str, api_key: str) -> str:
        if api_key:
            return api_key
        if provider == "gemini":
            raise TopicAnalysisDependencyError(
                "TOPIC_EMBEDDING_PROVIDER=gemini requires GEMINI_API_KEY or TOPIC_EMBEDDING_API_KEY."
            )
        if provider == "openai":
            raise TopicAnalysisDependencyError(
                "TOPIC_EMBEDDING_PROVIDER=openai requires OPENAI_API_KEY or TOPIC_EMBEDDING_API_KEY."
            )
        raise TopicAnalysisDependencyError(f"Unsupported topic embedding provider '{provider}'.")

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

    @staticmethod
    def _extract_http_error_payload(response: Any) -> dict[str, Any] | None:
        try:
            payload = response.json()
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    @classmethod
    def _extract_http_error(cls, response: Any) -> str:
        payload = cls._extract_http_error_payload(response)
        error = cls._extract_error_object(payload)
        if error is not None:
            message = error.get("message")
            if message:
                return str(message)

        if payload is not None:
            error_value = payload.get("error")
            if isinstance(error_value, str):
                return error_value
        return getattr(response, "text", "") or "No error details returned."

    @classmethod
    def _extract_error_object(cls, payload: dict[str, Any] | None) -> dict[str, Any] | None:
        if payload is None:
            return None

        error = payload.get("error")
        if isinstance(error, dict):
            return cls._parse_nested_error_object(error.get("message")) or error
        if isinstance(error, str):
            return cls._parse_nested_error_object(error)
        return None

    @staticmethod
    def _parse_nested_error_object(value: object) -> dict[str, Any] | None:
        if not isinstance(value, str):
            return None

        text = value.strip()
        if not text.startswith("{"):
            return None

        try:
            payload = json.loads(text)
        except ValueError:
            return None

        if not isinstance(payload, dict):
            return None

        nested_error = payload.get("error")
        if isinstance(nested_error, dict):
            return nested_error
        return payload

    def warm_up(
        self,
        *,
        model_name: str,
        provider: str = "gemini",
    ) -> None:
        return

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

    def _post_json_with_retries(
        self,
        *,
        requests_module: Any,
        provider: str,
        url: str,
        headers: dict[str, str],
        payload: dict[str, object],
        timeout_seconds: int,
    ) -> Any:
        for attempt in range(self.max_retries + 1):
            try:
                response = requests_module.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=timeout_seconds,
                )
            except requests_module.RequestException as exc:
                if attempt >= self.max_retries:
                    raise TopicAnalysisDependencyError(
                        f"{self._display_provider(provider)} embeddings request failed before a response was returned."
                    ) from exc
                self._sleep_before_retry(attempt=attempt, response=None)
                continue

            if self._should_return_retryable_gemini_rate_limit(provider=provider, response=response):
                return response

            if response.status_code in self.RETRYABLE_STATUS_CODES and attempt < self.max_retries:
                self._sleep_before_retry(attempt=attempt, response=response)
                continue
            return response

        raise TopicAnalysisDependencyError(
            f"{self._display_provider(provider)} embeddings request failed unexpectedly."
        )

    def _sleep_before_retry(self, *, attempt: int, response: Any | None) -> None:
        delay_seconds = self._retry_delay_seconds(attempt=attempt, response=response)
        if delay_seconds > 0:
            time.sleep(delay_seconds)

    def _retry_delay_seconds(self, *, attempt: int, response: Any | None) -> float:
        provider_retry_delay = self._provider_retry_delay_seconds(response)
        if provider_retry_delay is not None:
            return min(8.0, provider_retry_delay)

        return min(8.0, self.retry_base_seconds * (2 ** attempt))

    @classmethod
    def _provider_retry_delay_seconds(cls, response: Any | None) -> float | None:
        retry_after = cls._retry_after_header_seconds(response)
        if retry_after is not None:
            return retry_after

        payload = cls._extract_http_error_payload(response)
        error = cls._extract_error_object(payload)
        retry_delay = cls._retry_delay_from_error_details(error)
        if retry_delay is not None:
            return retry_delay

        if error is not None:
            return cls._retry_delay_from_text(error.get("message"))
        return None

    @staticmethod
    def _retry_after_header_seconds(response: Any | None) -> float | None:
        headers = getattr(response, "headers", {}) or {}
        retry_after = headers.get("Retry-After") if hasattr(headers, "get") else None
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                pass
        return None

    @classmethod
    def _retry_delay_from_error_details(cls, error: dict[str, Any] | None) -> float | None:
        details = error.get("details") if error is not None else None
        if not isinstance(details, list):
            return None

        for detail in details:
            if not isinstance(detail, dict):
                continue
            detail_type = str(detail.get("@type", ""))
            if detail_type.endswith("RetryInfo"):
                retry_delay = cls._parse_seconds_duration(detail.get("retryDelay"))
                if retry_delay is not None:
                    return retry_delay
        return None

    @staticmethod
    def _parse_seconds_duration(value: object) -> float | None:
        if isinstance(value, int | float):
            return max(0.0, float(value))
        if not isinstance(value, str):
            return None

        match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)s\s*", value)
        if not match:
            return None
        return max(0.0, float(match.group(1)))

    @classmethod
    def _retry_delay_from_text(cls, value: object) -> float | None:
        if not isinstance(value, str):
            return None

        match = re.search(r"retry\s+in\s+(\d+(?:\.\d+)?)\s*s", value, flags=re.IGNORECASE)
        if not match:
            return None
        return max(0.0, float(match.group(1)))

    def _raise_http_error(self, *, provider: str, response: Any) -> None:
        if provider == "gemini" and response.status_code == 429:
            self._raise_gemini_rate_limit_or_quota_error(response)

        message = self._extract_http_error(response)
        if response.status_code == 429:
            message = (
                f"{message} The embedding provider is rate-limited or out of quota. "
                "Try again later, switch TOPIC_EMBEDDING_PROVIDER, or configure TOPIC_EMBEDDING_FALLBACK_PROVIDER."
            )
        raise TopicAnalysisDependencyError(
            f"{self._display_provider(provider)} embeddings request failed ({response.status_code}): {message}"
        )

    def _raise_gemini_rate_limit_or_quota_error(self, response: Any) -> None:
        if self._is_daily_quota_error(response):
            raise TopicAnalysisDependencyError(
                "Gemini quota is exhausted for today. Try again after the daily quota resets."
            )

        raise TopicAnalysisRateLimitError(
            "Gemini is rate limited. Try again later.",
            error_code=self.GEMINI_RATE_LIMIT_ERROR_CODE,
            retry_after_seconds=self.GEMINI_RATE_LIMIT_RETRY_SECONDS,
        )

    @classmethod
    def _should_return_retryable_gemini_rate_limit(cls, *, provider: str, response: Any) -> bool:
        return (
            provider == "gemini"
            and getattr(response, "status_code", None) == 429
            and not cls._is_daily_quota_error(response)
        )

    @classmethod
    def _is_daily_quota_error(cls, response: Any) -> bool:
        payload = cls._extract_http_error_payload(response)
        error = cls._extract_error_object(payload)
        return any(cls._looks_like_daily_quota_signal(value) for value in cls._quota_signal_values(error))

    @staticmethod
    def _quota_signal_values(error: dict[str, Any] | None) -> list[str]:
        if error is None:
            return []

        values: list[str] = []
        message = error.get("message")
        if isinstance(message, str):
            values.append(message)

        details = error.get("details")
        if not isinstance(details, list):
            return values

        for detail in details:
            if not isinstance(detail, dict):
                continue
            detail_type = str(detail.get("@type", ""))
            if not detail_type.endswith("QuotaFailure"):
                continue
            violations = detail.get("violations")
            if not isinstance(violations, list):
                continue
            for violation in violations:
                if not isinstance(violation, dict):
                    continue
                for key in ("quotaId", "quotaMetric"):
                    value = violation.get(key)
                    if isinstance(value, str):
                        values.append(value)
        return values

    @staticmethod
    def _looks_like_daily_quota_signal(value: str) -> bool:
        normalized = re.sub(r"[^a-z0-9]+", "", value.casefold())
        return "perday" in normalized or "daily" in normalized or "rpd" in normalized

    def _store_cached_vectors(self, vectors_by_key: dict[str, Any]) -> None:
        if self.cache_size <= 0:
            return
        try:
            import numpy as np
        except Exception as exc:  # pragma: no cover - dependency error path
            raise TopicAnalysisDependencyError(
                "numpy is required for embedding-based analysis."
            ) from exc

        with self._cache_lock:
            for key, vector in vectors_by_key.items():
                cached_vector = np.asarray(vector, dtype=np.float32)
                cached_vector.setflags(write=False)
                self._cache[key] = cached_vector
                self._cache.move_to_end(key)
            while len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)

    @staticmethod
    def _cache_key(
        *,
        provider: str,
        model_name: str,
        dimensions: int,
        text: str,
    ) -> str:
        material = "\x1f".join(
            [
                provider,
                model_name,
                str(int(dimensions or 0)),
                text,
            ]
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    @staticmethod
    def _iter_batches(texts: list[str], batch_size: int):
        for index in range(0, len(texts), batch_size):
            yield texts[index:index + batch_size]
