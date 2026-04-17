"""Application settings loaded from environment variables (with optional .env file support)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.core.constants import DEFAULT_SESSION_SECRET

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
    topic_embedding_model: str = os.getenv(
        "TOPIC_EMBEDDING_MODEL",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    ).strip()
    topic_embedding_local_path: str = os.getenv(
        "TOPIC_EMBEDDING_LOCAL_PATH",
        "models/paraphrase-multilingual-MiniLM-L12-v2",
    ).strip()
    topic_kmeans_clusters: int = int(os.getenv("TOPIC_KMEANS_CLUSTERS", "8"))
    topic_kmeans_random_state: int = int(os.getenv("TOPIC_KMEANS_RANDOM_STATE", "42"))
    topic_hdbscan_min_cluster_size: int = int(os.getenv("TOPIC_HDBSCAN_MIN_CLUSTER_SIZE", "5"))
    topic_hdbscan_min_samples: int = int(os.getenv("TOPIC_HDBSCAN_MIN_SAMPLES", "3"))
    topic_hdbscan_metric: str = os.getenv("TOPIC_HDBSCAN_METRIC", "euclidean").strip()
    topic_bertopic_language: str = os.getenv("TOPIC_BERTOPIC_LANGUAGE", "multilingual").strip()
    topic_bertopic_reduce_outliers: bool = os.getenv("TOPIC_BERTOPIC_REDUCE_OUTLIERS", "true").strip().casefold() in {"1", "true", "yes", "on"}
    topic_bertopic_outlier_threshold: float = float(os.getenv("TOPIC_BERTOPIC_OUTLIER_THRESHOLD", "0.0"))
    topic_top_terms: int = int(os.getenv("TOPIC_TOP_TERMS", "6"))
    topic_top_ngrams: int = int(os.getenv("TOPIC_TOP_NGRAMS", "12"))
    topic_representative_examples: int = int(os.getenv("TOPIC_REPRESENTATIVE_EXAMPLES", "3"))
    topic_max_document_chars: int = int(os.getenv("TOPIC_MAX_DOCUMENT_CHARS", "3000"))
    topic_translation_enabled: bool = os.getenv("TOPIC_TRANSLATION_ENABLED", "true").strip().casefold() in {"1", "true", "yes", "on"}
    topic_translation_source_language: str = os.getenv("TOPIC_TRANSLATION_SOURCE_LANGUAGE", "auto").strip()
    topic_translation_target_language: str = os.getenv("TOPIC_TRANSLATION_TARGET_LANGUAGE", "en").strip()
    topic_translation_batch_size: int = int(os.getenv("TOPIC_TRANSLATION_BATCH_SIZE", "8"))
    topic_ai_labeling_enabled: bool = os.getenv("TOPIC_AI_LABELING_ENABLED", "true").strip().casefold() in {"1", "true", "yes", "on"}
    topic_ai_labeling_timeout_seconds: int = int(os.getenv("TOPIC_AI_LABELING_TIMEOUT_SECONDS", "30"))
    topic_ai_labeling_max_groups: int = int(os.getenv("TOPIC_AI_LABELING_MAX_GROUPS", "10"))
    topic_ai_labeling_max_examples: int = int(os.getenv("TOPIC_AI_LABELING_MAX_EXAMPLES", "3"))
    topic_ai_labeling_max_terms: int = int(os.getenv("TOPIC_AI_LABELING_MAX_TERMS", "4"))
    topic_ai_labeling_max_chars_per_example: int = int(os.getenv("TOPIC_AI_LABELING_MAX_CHARS_PER_EXAMPLE", "220"))
    session_secret: str = os.getenv("SESSION_SECRET", DEFAULT_SESSION_SECRET).strip()
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

    @property
    def is_default_session_secret(self) -> bool:
        """True when the session secret has not been overridden from the insecure placeholder."""
        return self.session_secret == DEFAULT_SESSION_SECRET

    @property
    def debug(self) -> bool:
        """True in any local/test environment; controls security guards such as the session-secret check."""
        return self.app_env in {"development", "dev", "local", "test"}


def get_settings() -> Settings:
    """Create a fresh Settings instance (re-reads env vars on each call)."""
    return Settings()
