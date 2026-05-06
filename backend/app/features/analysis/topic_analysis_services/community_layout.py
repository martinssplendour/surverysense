"""Graph layout helpers for community detection."""
from __future__ import annotations

from typing import Any


class CommunityLayoutMixin:
    """NetworkX layout behavior."""

    @classmethod
    def _build_layout_positions(
        cls,
        embedding_array: Any,
        graph: Any,
        nx: Any,
        np: Any,
    ) -> dict[int, tuple[float, float]]:
        """2D layout for scatter visualization.

        Uses NetworkX graph layout so topic membership and visualization are based
        on the same graph, without dimensionality reduction changing distances.
        """
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
