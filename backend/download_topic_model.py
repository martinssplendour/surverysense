from __future__ import annotations

import logging
from pathlib import Path

from app.core.settings import get_settings

logger = logging.getLogger("topic-model-download")


def _resolve_local_model_path(local_model_path: str) -> Path:
    candidate_path = Path(local_model_path).expanduser()
    if candidate_path.is_absolute():
        return candidate_path
    return Path(__file__).resolve().parent / candidate_path


def _has_model_files(model_path: Path) -> bool:
    return (
        model_path.exists()
        and any(model_path.rglob("*.json"))
        and (any(model_path.rglob("*.safetensors")) or any(model_path.rglob("*.bin")))
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    if not settings.topic_embedding_local_path:
        logger.info("TOPIC_EMBEDDING_LOCAL_PATH is empty. Skipping local model download.")
        return

    local_model_path = _resolve_local_model_path(settings.topic_embedding_local_path)
    if _has_model_files(local_model_path):
        logger.info("Topic model already present at %s", local_model_path)
        return

    try:
        from huggingface_hub import snapshot_download
    except Exception as exc:  # pragma: no cover - dependency error path
        raise RuntimeError(
            "huggingface-hub is required to download the local topic model."
        ) from exc

    local_model_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(
        "Downloading topic embedding model '%s' into %s",
        settings.topic_embedding_model,
        local_model_path,
    )
    snapshot_download(
        repo_id=settings.topic_embedding_model,
        local_dir=str(local_model_path),
    )


if __name__ == "__main__":
    main()
