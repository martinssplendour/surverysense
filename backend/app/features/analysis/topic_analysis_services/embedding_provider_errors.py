"""HTTP retry, quota, and provider error helpers for hosted embeddings."""
from __future__ import annotations

import json
import re
import time
from typing import Any

from app.core.exceptions import TopicAnalysisDependencyError, TopicAnalysisRateLimitError


class EmbeddingProviderErrorMixin:
    """Shared provider error handling for hosted embedding services."""

    @staticmethod
    def _normalise_provider(provider: str) -> str:
        return (provider or "gemini").strip().casefold()

    @staticmethod
    def _display_provider(provider: str) -> str:
        normalized = EmbeddingProviderErrorMixin._normalise_provider(provider)
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
