"""Embedding reduction and graph layout helpers for community detection."""
from __future__ import annotations

from importlib import metadata
from typing import Any


class CommunityLayoutMixin:
    """UMAP reduction and fallback layout behavior."""

    @classmethod
    def _reduce_for_clustering(cls, embedding_array: Any, np: Any, *, warnings: list[str] | None = None) -> tuple[Any, bool]:
        """UMAP reduction to 15 dims before graph construction.

        Only applied when the embedding space is high-dimensional enough to benefit
        (>15 dims) and the corpus is large enough for UMAP to be stable (>=10 docs).
        Falls back to raw embeddings if umap-learn is not installed.
        """
        n_docs, n_dims = int(embedding_array.shape[0]), int(embedding_array.shape[1])
        if n_docs < 10 or n_dims <= 15:
            return embedding_array, False
        if cls._has_incompatible_umap_runtime():
            if warnings is not None:
                warnings.append(
                    "UMAP clustering reduction was skipped because the installed umap-learn and scikit-learn versions are incompatible, so community detection used the original embeddings."
                )
            return embedding_array, False
        try:
            import umap as umap_lib
        except ImportError:  # pragma: no cover - optional dependency
            return embedding_array, False

        n_components = min(30, n_docs - 2)
        n_neighbors = min(15, n_docs - 1)
        reducer = umap_lib.UMAP(
            n_components=n_components,
            n_neighbors=n_neighbors,
            min_dist=0.0,
            metric="cosine",
            random_state=42,
            low_memory=False,
        )
        try:
            return np.asarray(reducer.fit_transform(embedding_array), dtype=np.float32), True
        except Exception:  # pragma: no cover - depends on optional dependency versions
            if warnings is not None:
                warnings.append(
                    "UMAP clustering reduction was skipped because dimensionality reduction failed, so community detection used the original embeddings."
                )
            return embedding_array, False

    @staticmethod
    def _has_incompatible_umap_runtime() -> bool:
        try:
            umap_version = metadata.version("umap-learn")
            sklearn_version = metadata.version("scikit-learn")
        except metadata.PackageNotFoundError:
            return False

        umap_major_minor = CommunityLayoutMixin._major_minor_version(umap_version)
        sklearn_major_minor = CommunityLayoutMixin._major_minor_version(sklearn_version)
        if umap_major_minor is None or sklearn_major_minor is None:
            return False
        return umap_major_minor < (0, 6) and sklearn_major_minor >= (1, 8)

    @staticmethod
    def _major_minor_version(version: str) -> tuple[int, int] | None:
        parsed_parts: list[int] = []
        for part in version.split(".")[:2]:
            digits = []
            for character in part:
                if not character.isdigit():
                    break
                digits.append(character)
            if not digits:
                return None
            parsed_parts.append(int("".join(digits)))
        if len(parsed_parts) < 2:
            return None
        return parsed_parts[0], parsed_parts[1]

    @classmethod
    def _build_layout_positions(
        cls,
        embedding_array: Any,
        graph: Any,
        nx: Any,
        np: Any,
        reduced_embeddings: Any | None = None,
    ) -> dict[int, tuple[float, float]]:
        """2D layout for scatter visualization.

        Uses UMAP when the corpus and embedding dimensions are large enough for it
        to produce a semantically meaningful layout. Falls back to NetworkX graph
        layout (circular when no edges, spring otherwise) for small or low-dim data.
        """
        n_docs, n_dims = int(embedding_array.shape[0]), int(embedding_array.shape[1])
        if reduced_embeddings is not None:
            positions = cls._positions_from_reduced_embeddings(reduced_embeddings, np)
            if positions:
                return positions

        if (
            n_docs >= 4
            and n_dims > 2
            and not cls._has_incompatible_umap_runtime()
        ):
            try:
                import umap as umap_lib

                n_neighbors = min(15, n_docs - 1)
                reducer = umap_lib.UMAP(
                    n_components=2,
                    n_neighbors=n_neighbors,
                    min_dist=0.1,
                    metric="cosine",
                    random_state=42,
                )
                positions_2d = reducer.fit_transform(embedding_array)
                return {
                    i: (round(float(positions_2d[i, 0]), 6), round(float(positions_2d[i, 1]), 6))
                    for i in range(n_docs)
                }
            except Exception:  # pragma: no cover - optional dependency or edge case
                pass

        if graph.number_of_nodes() == 1:
            return {int(next(iter(graph.nodes))): (0.0, 0.0)}
        if graph.number_of_edges() == 0:
            positions = nx.circular_layout(graph)
        else:
            positions = nx.spring_layout(graph, seed=42, weight="weight")
        return {
            int(node_id): (round(float(position[0]), 6), round(float(position[1]), 6))
            for node_id, position in positions.items()
        }

    @staticmethod
    def _normalize_rows(embedding_array: Any, np: Any) -> Any:
        norms = np.linalg.norm(embedding_array, axis=1, keepdims=True)
        return np.divide(
            embedding_array,
            norms,
            out=np.zeros_like(embedding_array),
            where=norms != 0,
        )

    @staticmethod
    def _positions_from_reduced_embeddings(reduced_embeddings: Any, np: Any) -> dict[int, tuple[float, float]]:
        reduced_array = np.asarray(reduced_embeddings, dtype=np.float32)
        if reduced_array.ndim != 2 or int(reduced_array.shape[0]) == 0 or int(reduced_array.shape[1]) < 2:
            return {}
        return {
            i: (round(float(reduced_array[i, 0]), 6), round(float(reduced_array[i, 1]), 6))
            for i in range(int(reduced_array.shape[0]))
        }
