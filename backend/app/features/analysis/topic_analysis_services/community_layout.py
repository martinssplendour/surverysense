"""UMAP candidate projection and graph layout helpers for community detection."""
from __future__ import annotations

from importlib import metadata
from typing import Any


class CommunityLayoutMixin:
    """UMAP-assisted candidate search and visualization behavior."""

    @classmethod
    def _build_candidate_projection(
        cls,
        embedding_array: Any,
        np: Any,
        *,
        warnings: list[str] | None = None,
    ) -> Any:
        """Project embeddings for neighbor candidate search only.

        Candidate projection narrows which local neighbors are considered. Final
        graph edges are still verified against original embedding cosine similarity.
        """
        n_docs, n_dims = int(embedding_array.shape[0]), int(embedding_array.shape[1])
        if n_docs < 10 or n_dims <= 30:
            return embedding_array
        if cls._has_incompatible_umap_runtime():
            if warnings is not None:
                warnings.append(
                    "UMAP candidate projection was skipped because the installed umap-learn and scikit-learn versions are incompatible."
                )
            return embedding_array
        try:
            import umap as umap_lib
        except ImportError:
            if warnings is not None:
                warnings.append(
                    "UMAP candidate projection was skipped because umap-learn is not installed."
                )
            return embedding_array

        reducer = umap_lib.UMAP(
            n_components=min(30, n_docs - 2),
            n_neighbors=min(15, n_docs - 1),
            min_dist=0.0,
            metric="cosine",
            random_state=42,
            low_memory=False,
        )
        try:
            return np.asarray(reducer.fit_transform(embedding_array), dtype=np.float32)
        except Exception:
            if warnings is not None:
                warnings.append(
                    "UMAP candidate projection was skipped because dimensionality reduction failed."
                )
            return embedding_array

    @classmethod
    def _build_layout_positions(
        cls,
        embedding_array: Any,
        graph: Any,
        nx: Any,
        np: Any,
    ) -> dict[int, tuple[float, float]]:
        """2D layout for scatter visualization.

        UMAP is used only for visualization when available. Topic membership is
        determined by graph edges verified in original embedding space.
        """
        umap_positions = cls._build_umap_layout_positions(embedding_array, np)
        if umap_positions:
            return umap_positions

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

    @classmethod
    def _build_umap_layout_positions(cls, embedding_array: Any, np: Any) -> dict[int, tuple[float, float]]:
        n_docs, n_dims = int(embedding_array.shape[0]), int(embedding_array.shape[1])
        if n_docs < 4 or n_dims <= 2 or cls._has_incompatible_umap_runtime():
            return {}
        try:
            import umap as umap_lib
        except ImportError:
            return {}

        reducer = umap_lib.UMAP(
            n_components=2,
            n_neighbors=min(15, n_docs - 1),
            min_dist=0.1,
            metric="cosine",
            random_state=42,
        )
        try:
            positions_2d = np.asarray(reducer.fit_transform(embedding_array), dtype=np.float32)
        except Exception:
            return {}
        return {
            i: (round(float(positions_2d[i, 0]), 6), round(float(positions_2d[i, 1]), 6))
            for i in range(n_docs)
        }

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
