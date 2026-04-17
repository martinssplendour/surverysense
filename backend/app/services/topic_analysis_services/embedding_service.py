"""Loads and caches sentence-transformer models; encodes text lists to L2-normalised embedding arrays."""
from __future__ import annotations

from pathlib import Path
from threading import Lock

from app.core.exceptions import TopicAnalysisDependencyError


class SentenceEmbeddingService:
    """Thread-safe, process-local cache of SentenceTransformer models keyed by resolved model path."""

    def __init__(self) -> None:
        self._models: dict[str, object] = {}
        self._lock = Lock()

    def _resolve_model_source(
        self,
        *,
        model_name: str,
        local_model_path: str,
    ) -> tuple[str, bool]:
        """Return (source_path_or_name, is_local_only) — prefers a local filesystem path over HuggingFace Hub."""
        if local_model_path:
            candidate_path = Path(local_model_path).expanduser()
            if not candidate_path.is_absolute():
                candidate_path = Path(__file__).resolve().parents[3] / local_model_path
            if candidate_path.exists():
                return (str(candidate_path), True)
        return (model_name, False)

    def _get_model(self, model_name: str, *, local_model_path: str = ""):
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as exc:  # pragma: no cover - dependency error path
            raise TopicAnalysisDependencyError(
                "sentence-transformers is required for embedding-based analysis."
            ) from exc

        model_source, local_only = self._resolve_model_source(
            model_name=model_name,
            local_model_path=local_model_path,
        )
        with self._lock:
            model = self._models.get(model_source)
            if model is None:
                load_kwargs: dict[str, object] = {}
                if local_only:
                    load_kwargs["local_files_only"] = True
                model = SentenceTransformer(model_source, **load_kwargs)
                self._models[model_source] = model
        return model

    def warm_up(self, *, model_name: str, local_model_path: str = "") -> None:
        if not model_name:
            return
        model = self._get_model(model_name, local_model_path=local_model_path)
        # Run a dummy encode to trigger PyTorch and Numba JIT compilation at startup.
        # Without this, the first real request pays a ~20s JIT cold-start penalty on the
        # first batch regardless of model caching.
        try:
            model.encode(["warmup"], show_progress_bar=False, normalize_embeddings=True)
        except Exception:
            pass

    def encode(self, texts: list[str], *, model_name: str, local_model_path: str = ""):
        """Encode texts to a numpy float array of L2-normalised embeddings using batch_size=64."""
        if not texts:
            return []

        try:
            import numpy as np
        except Exception as exc:  # pragma: no cover - dependency error path
            raise TopicAnalysisDependencyError(
                "numpy is required for embedding-based analysis."
            ) from exc

        model = self._get_model(model_name, local_model_path=local_model_path)

        embeddings = model.encode(
            texts,
            show_progress_bar=False,
            normalize_embeddings=True,
            batch_size=64,  # default=32; larger batches reduce dispatch overhead on CPU
        )
        return np.array(embeddings)
