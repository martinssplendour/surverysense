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
    architect_sample_size: int = int(os.getenv("ARCHITECT_SAMPLE_SIZE", "15"))
    row_limit: int = int(os.getenv("TRANSFORM_ROW_LIMIT", "5000"))
    transformed_preview_size: int = int(os.getenv("TRANSFORM_PREVIEW_SIZE", "25"))
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "").strip()
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    gemini_temperature: float = float(os.getenv("GEMINI_TEMPERATURE", "0.1"))
    gemini_timeout_seconds: int = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "60"))


def get_settings() -> Settings:
    return Settings()
