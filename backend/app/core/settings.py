"""Application settings loaded from environment variables (with optional .env file support)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional until dependencies are installed.
    load_dotenv = None


def _load_env_file() -> None:
    if load_dotenv is None:
        return
    env_path = Path(__file__).resolve().parents[2] / ".env"
    load_dotenv(env_path, override=False)


_load_env_file()


def _parse_csv_env(name: str) -> tuple[str, ...]:
    return tuple(
        item.strip()
        for item in os.getenv(name, "").split(",")
        if item.strip()
    )


@dataclass(slots=True)
class Settings:
    """All runtime configuration values, each read from an environment variable with a safe default."""
    app_env: str = os.getenv("APP_ENV", "development").strip().casefold() or "development"
    ingest_sample_size: int = int(os.getenv("INGEST_SAMPLE_SIZE", "25"))
    architect_sample_size: int = int(os.getenv("ARCHITECT_SAMPLE_SIZE", "25"))
    row_limit: int = int(os.getenv("TRANSFORM_ROW_LIMIT", "5000"))
    result_store_max_results: int = int(os.getenv("RESULT_STORE_MAX_RESULTS", "8"))
    result_store_ttl_seconds: int = int(os.getenv("RESULT_STORE_TTL_SECONDS", "900"))
    result_store_cleanup_interval_seconds: int = int(os.getenv("RESULT_STORE_CLEANUP_INTERVAL_SECONDS", "60"))
    topic_embedding_provider: str = os.getenv("TOPIC_EMBEDDING_PROVIDER", "gemini").strip().casefold() or "gemini"
    topic_embedding_model: str = os.getenv("TOPIC_EMBEDDING_MODEL", "").strip()
    topic_embedding_api_key: str = os.getenv("TOPIC_EMBEDDING_API_KEY", "").strip()
    topic_embedding_dimensions: int = int(os.getenv("TOPIC_EMBEDDING_DIMENSIONS", "3072"))
    topic_embedding_batch_size: int = int(os.getenv("TOPIC_EMBEDDING_BATCH_SIZE", "128"))
    topic_embedding_timeout_seconds: int = int(os.getenv("TOPIC_EMBEDDING_TIMEOUT_SECONDS", "60"))
    topic_embedding_max_retries: int = int(os.getenv("TOPIC_EMBEDDING_MAX_RETRIES", "1"))
    topic_embedding_retry_base_seconds: float = float(os.getenv("TOPIC_EMBEDDING_RETRY_BASE_SECONDS", "0.75"))
    topic_embedding_cache_size: int = int(os.getenv("TOPIC_EMBEDDING_CACHE_SIZE", "512"))
    topic_embedding_fallback_provider: str = os.getenv("TOPIC_EMBEDDING_FALLBACK_PROVIDER", "openai").strip().casefold()
    topic_embedding_fallback_model: str = os.getenv("TOPIC_EMBEDDING_FALLBACK_MODEL", "").strip()
    topic_embedding_fallback_api_key: str = os.getenv("TOPIC_EMBEDDING_FALLBACK_API_KEY", "").strip()
    topic_community_similarity_threshold: float = float(os.getenv("TOPIC_COMMUNITY_SIMILARITY_THRESHOLD", "0.89"))
    topic_community_max_neighbors: int = int(os.getenv("TOPIC_COMMUNITY_MAX_NEIGHBORS", "16"))
    topic_community_resolution: float = float(os.getenv("TOPIC_COMMUNITY_RESOLUTION", "0.9"))
    topic_community_mutual_neighbors: bool = os.getenv("TOPIC_COMMUNITY_MUTUAL_NEIGHBORS", "true").strip().casefold() in {"1", "true", "yes", "on"}
    topic_top_terms: int = int(os.getenv("TOPIC_TOP_TERMS", "6"))
    topic_top_ngrams: int = int(os.getenv("TOPIC_TOP_NGRAMS", "12"))
    topic_representative_examples: int = int(os.getenv("TOPIC_REPRESENTATIVE_EXAMPLES", "3"))
    topic_max_document_chars: int = int(os.getenv("TOPIC_MAX_DOCUMENT_CHARS", "3000"))
    topic_input_translation_enabled: bool = os.getenv("TOPIC_INPUT_TRANSLATION_ENABLED", "false").strip().casefold() in {"1", "true", "yes", "on"}
    topic_translation_enabled: bool = os.getenv("TOPIC_TRANSLATION_ENABLED", "true").strip().casefold() in {"1", "true", "yes", "on"}
    topic_translation_source_language: str = os.getenv("TOPIC_TRANSLATION_SOURCE_LANGUAGE", "auto").strip()
    topic_translation_target_language: str = os.getenv("TOPIC_TRANSLATION_TARGET_LANGUAGE", "en").strip()
    topic_translation_batch_size: int = int(os.getenv("TOPIC_TRANSLATION_BATCH_SIZE", "8"))
    topic_ai_labeling_enabled: bool = os.getenv("TOPIC_AI_LABELING_ENABLED", "true").strip().casefold() in {"1", "true", "yes", "on"}
    topic_ai_labeling_model: str = os.getenv("TOPIC_AI_LABELING_MODEL", "gemini-2.5-pro").strip()
    topic_ai_labeling_timeout_seconds: int = int(os.getenv("TOPIC_AI_LABELING_TIMEOUT_SECONDS", "30"))
    topic_ai_labeling_max_groups: int = int(os.getenv("TOPIC_AI_LABELING_MAX_GROUPS", "0"))
    topic_ai_labeling_max_examples: int = int(os.getenv("TOPIC_AI_LABELING_MAX_EXAMPLES", "50"))
    topic_ai_labeling_max_terms: int = int(os.getenv("TOPIC_AI_LABELING_MAX_TERMS", "4"))
    topic_ai_labeling_max_unigrams: int = int(os.getenv("TOPIC_AI_LABELING_MAX_UNIGRAMS", "5"))
    topic_ai_labeling_max_bigrams: int = int(os.getenv("TOPIC_AI_LABELING_MAX_BIGRAMS", "3"))
    topic_ai_labeling_max_trigrams: int = int(os.getenv("TOPIC_AI_LABELING_MAX_TRIGRAMS", "3"))
    topic_ai_labeling_min_ngram_document_count: int = int(os.getenv("TOPIC_AI_LABELING_MIN_NGRAM_DOCUMENT_COUNT", "4"))
    topic_ai_labeling_max_chars_per_example: int = int(os.getenv("TOPIC_AI_LABELING_MAX_CHARS_PER_EXAMPLE", "220"))
    topic_ai_labeling_batch_size: int = int(os.getenv("TOPIC_AI_LABELING_BATCH_SIZE", "10"))
    topic_ai_labeling_max_retries: int = int(os.getenv("TOPIC_AI_LABELING_MAX_RETRIES", "1"))
    topic_ai_labeling_retry_base_seconds: float = float(os.getenv("TOPIC_AI_LABELING_RETRY_BASE_SECONDS", "0.75"))
    topic_ai_labeling_consolidate_similar_labels: bool = os.getenv(
        "TOPIC_AI_LABELING_CONSOLIDATE_SIMILAR_LABELS", "true"
    ).strip().casefold() in {"1", "true", "yes", "on"}
    session_secret: str = os.getenv("SESSION_SECRET", "").strip()
    session_https_only: bool = os.getenv("SESSION_HTTPS_ONLY", "false").strip().casefold() in {"1", "true", "yes", "on"}
    session_idle_timeout_seconds: int = int(os.getenv("SESSION_IDLE_TIMEOUT_SECONDS", "1800"))
    google_oauth_client_id: str = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    google_oauth_client_secret: str = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
    google_oauth_redirect_uris: tuple[str, ...] = _parse_csv_env("GOOGLE_OAUTH_REDIRECT_URIS")
    google_oauth_javascript_origins: tuple[str, ...] = _parse_csv_env("GOOGLE_OAUTH_JAVASCRIPT_ORIGINS")
    google_oauth_client_json_path: str = os.getenv("GOOGLE_OAUTH_CLIENT_JSON_PATH", "").strip()
    google_oauth_allowed_domains: tuple[str, ...] = _parse_csv_env("GOOGLE_OAUTH_ALLOWED_DOMAINS") or (
        "twinkl.co.uk",
        "twinkl.com",
    )
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "").strip()
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    gemini_temperature: float = float(os.getenv("GEMINI_TEMPERATURE", "0.1"))
    gemini_timeout_seconds: int = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "60"))
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "").strip()

    @property
    def debug(self) -> bool:
        """True in any local/test environment."""
        return self.app_env in {"development", "dev", "local", "test"}

    @property
    def resolved_topic_embedding_model(self) -> str:
        """Provider-aware embedding model default."""
        if self.topic_embedding_model:
            return self.topic_embedding_model
        return self._default_topic_embedding_model(self.topic_embedding_provider)

    @property
    def resolved_topic_embedding_api_key(self) -> str:
        if self.topic_embedding_api_key:
            return self.topic_embedding_api_key
        return self._topic_embedding_api_key_for_provider(self.topic_embedding_provider)

    @property
    def resolved_topic_embedding_fallback_provider(self) -> str:
        provider = (self.topic_embedding_fallback_provider or "").strip().casefold()
        if provider in {"", "none", "off", "false", "disabled"}:
            return ""
        if provider == self.topic_embedding_provider:
            return ""
        if provider not in {"gemini", "openai"}:
            return ""
        if not self.resolved_topic_embedding_fallback_api_key:
            return ""
        return provider

    @property
    def resolved_topic_embedding_fallback_model(self) -> str:
        provider = (self.topic_embedding_fallback_provider or "").strip().casefold()
        if not self.resolved_topic_embedding_fallback_provider:
            return ""
        if self.topic_embedding_fallback_model:
            return self.topic_embedding_fallback_model
        return self._default_topic_embedding_model(provider)

    @property
    def resolved_topic_embedding_fallback_api_key(self) -> str:
        provider = (self.topic_embedding_fallback_provider or "").strip().casefold()
        if provider in {"", "none", "off", "false", "disabled"}:
            return ""
        if self.topic_embedding_fallback_api_key:
            return self.topic_embedding_fallback_api_key
        return self._topic_embedding_api_key_for_provider(provider)

    @staticmethod
    def _default_topic_embedding_model(provider: str) -> str:
        if provider == "openai":
            return "text-embedding-3-small"
        return "gemini-embedding-001"

    def _topic_embedding_api_key_for_provider(self, provider: str) -> str:
        if provider == "openai":
            return self.openai_api_key
        if provider == "gemini":
            return self.gemini_api_key
        return ""


def get_settings() -> Settings:
    """Create a fresh Settings instance (re-reads env vars on each call)."""
    return Settings()
