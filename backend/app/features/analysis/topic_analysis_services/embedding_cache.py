"""In-memory LRU cache helpers for hosted embedding vectors."""
from __future__ import annotations

import hashlib
from typing import Any

from app.core.exceptions import TopicAnalysisDependencyError


class EmbeddingCacheMixin:
    """Cache helpers used by the public sentence embedding service."""

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
