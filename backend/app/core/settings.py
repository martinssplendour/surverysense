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


@dataclass(slots=True)
class Settings:
    ingest_sample_size: int = int(os.getenv("INGEST_SAMPLE_SIZE", "25"))
    architect_sample_size: int = int(os.getenv("ARCHITECT_SAMPLE_SIZE", "25"))
    row_limit: int = int(os.getenv("TRANSFORM_ROW_LIMIT", "5000"))
    transformed_preview_size: int = int(os.getenv("TRANSFORM_PREVIEW_SIZE", "25"))
    topic_embedding_model: str = os.getenv(
        "TOPIC_EMBEDDING_MODEL",
        "sentence-transformers/all-mpnet-base-v2",
    ).strip()
    topic_kmeans_clusters: int = int(os.getenv("TOPIC_KMEANS_CLUSTERS", "8"))
    topic_kmeans_random_state: int = int(os.getenv("TOPIC_KMEANS_RANDOM_STATE", "42"))
    topic_hdbscan_min_cluster_size: int = int(os.getenv("TOPIC_HDBSCAN_MIN_CLUSTER_SIZE", "5"))
    topic_hdbscan_min_samples: int = int(os.getenv("TOPIC_HDBSCAN_MIN_SAMPLES", "3"))
    topic_hdbscan_metric: str = os.getenv("TOPIC_HDBSCAN_METRIC", "euclidean").strip()
    topic_bertopic_language: str = os.getenv("TOPIC_BERTOPIC_LANGUAGE", "multilingual").strip()
    topic_top_terms: int = int(os.getenv("TOPIC_TOP_TERMS", "6"))
    topic_top_ngrams: int = int(os.getenv("TOPIC_TOP_NGRAMS", "12"))
    topic_representative_examples: int = int(os.getenv("TOPIC_REPRESENTATIVE_EXAMPLES", "3"))
    topic_max_document_chars: int = int(os.getenv("TOPIC_MAX_DOCUMENT_CHARS", "3000"))
    session_secret: str = os.getenv("SESSION_SECRET", "verbatim-app-dev-session-secret-change-me").strip()
    session_https_only: bool = os.getenv("SESSION_HTTPS_ONLY", "false").strip().casefold() in {"1", "true", "yes", "on"}
    google_oauth_client_json_path: str = os.getenv("GOOGLE_OAUTH_CLIENT_JSON_PATH", "").strip()
    google_oauth_allowed_domains: tuple[str, ...] = tuple(
        domain.strip()
        for domain in os.getenv("GOOGLE_OAUTH_ALLOWED_DOMAINS", "twinkl.co.uk,twinkl.com").split(",")
        if domain.strip()
    )
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "").strip()
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    gemini_temperature: float = float(os.getenv("GEMINI_TEMPERATURE", "0.1"))
    gemini_timeout_seconds: int = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "60"))


def get_settings() -> Settings:
    return Settings()
