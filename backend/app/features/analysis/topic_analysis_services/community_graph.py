"""Graph construction and community assignment helpers."""
from __future__ import annotations

from typing import Any

from app.features.analysis.topic_analysis_services.contracts import TopicModelGroupDefinition


class CommunityGraphMixin:
    """Similarity graph and community assignment primitives."""

    @classmethod
    def _detect_communities(
        cls,
        graph: Any,
        *,
        document_count: int,
        resolution: float,
        nx: Any,
    ) -> tuple[list[set[int]], str | None]:
        try:
            communities = cls._detect_leiden_communities(
                graph,
                document_count=document_count,
                resolution=resolution,
            )
            return cls._order_communities(communities), None
        except ImportError:
            communities = cls._detect_greedy_modularity_communities(graph, nx)
            return (
                cls._order_communities(communities),
                "Leiden community detection is not installed, so NetworkX greedy modularity was used.",
            )
        except Exception as exc:  # pragma: no cover - defensive dependency guard
            communities = cls._detect_greedy_modularity_communities(graph, nx)
            return (
                cls._order_communities(communities),
                f"Leiden community detection failed ({type(exc).__name__}), so NetworkX greedy modularity was used.",
            )

    @staticmethod
    def _detect_leiden_communities(
        graph: Any,
        *,
        document_count: int,
        resolution: float,
    ) -> list[set[int]]:
        try:
            import igraph as ig
            import leidenalg
        except ImportError:
            raise

        edge_rows = [
            (int(source), int(target), float(data.get("weight", 0.0)))
            for source, target, data in sorted(graph.edges(data=True), key=lambda edge: (edge[0], edge[1]))
        ]
        igraph_graph = ig.Graph()
        igraph_graph.add_vertices(document_count)
        igraph_graph.add_edges([(source, target) for source, target, _weight in edge_rows])
        igraph_graph.es["weight"] = [weight for _source, _target, weight in edge_rows]

        partition = leidenalg.find_partition(
            igraph_graph,
            leidenalg.RBConfigurationVertexPartition,
            weights="weight",
            resolution_parameter=max(0.05, float(resolution or 1.0)),
            n_iterations=-1,
            seed=42,
        )
        membership = list(partition.membership)
        if len(membership) != document_count:
            raise ValueError("Leiden returned an invalid community membership vector.")

        communities_by_id: dict[int, set[int]] = {}
        for row_index, community_id in enumerate(membership):
            communities_by_id.setdefault(int(community_id), set()).add(int(row_index))
        return list(communities_by_id.values())

    @staticmethod
    def _detect_greedy_modularity_communities(graph: Any, nx: Any) -> list[set[int]]:
        return [set(community) for community in nx.algorithms.community.greedy_modularity_communities(graph, weight="weight")]

    @classmethod
    def _build_candidate_neighbors(
        cls,
        normalized_embeddings: Any,
        *,
        threshold: float,
        language_edge_threshold: float,
        neighbor_limit: int,
        np: Any,
        languages: list[str | None] | None = None,
    ) -> list[dict[int, float]]:
        candidate_neighbors: list[dict[int, float]] = []
        document_count = int(normalized_embeddings.shape[0])
        for row_index in range(document_count):
            similarities = normalized_embeddings @ normalized_embeddings[row_index]
            similarities[row_index] = -1.0
            candidate_indices = cls._top_candidate_indices(
                similarities,
                neighbor_limit=neighbor_limit,
                np=np,
            )
            row_neighbors: dict[int, float] = {}
            for candidate_index in candidate_indices:
                neighbor_index = int(candidate_index)
                similarity = float(similarities[neighbor_index])
                required_threshold = cls._pair_similarity_threshold(
                    source_index=row_index,
                    target_index=neighbor_index,
                    base_threshold=threshold,
                    language_edge_threshold=language_edge_threshold,
                    languages=languages,
                )
                if similarity >= required_threshold:
                    row_neighbors[neighbor_index] = similarity
            candidate_neighbors.append(row_neighbors)
        return candidate_neighbors

    @classmethod
    def _assign_communities_with_noise(
        cls,
        communities: list[set[int]],
        *,
        document_count: int,
    ) -> tuple[list[int], dict[str, TopicModelGroupDefinition], int]:
        assignments = [cls.NOISE_GROUP_ID] * document_count
        explicit_groups: dict[str, TopicModelGroupDefinition] = {}
        valid_communities: list[set[int]] = []
        noise_nodes: set[int] = set()

        for community in communities:
            if cls._is_noise_community(community, document_count=document_count):
                noise_nodes.update(int(node_index) for node_index in community)
            else:
                valid_communities.append(community)

        for community_id, community in enumerate(cls._order_communities(valid_communities)):
            for node_index in community:
                assignments[int(node_index)] = int(community_id)

        if noise_nodes:
            explicit_groups[str(cls.NOISE_GROUP_ID)] = TopicModelGroupDefinition(is_noise=True)
            for node_index in noise_nodes:
                assignments[int(node_index)] = cls.NOISE_GROUP_ID

        return assignments, explicit_groups, len(noise_nodes)

    @classmethod
    def _is_noise_community(cls, community: set[int], *, document_count: int) -> bool:
        if len(community) <= 1:
            return True
        if document_count >= cls.MIN_TOPIC_SAMPLE_SIZE_FOR_SIZE_RULE and len(community) < cls.MIN_TOPIC_COMMUNITY_SIZE:
            return True
        return False

    @staticmethod
    def _add_similarity_edges(
        graph: Any,
        *,
        candidate_neighbors: list[dict[int, float]],
        mutual_neighbors: bool,
    ) -> None:
        for source_index, neighbors in enumerate(candidate_neighbors):
            for target_index, similarity in neighbors.items():
                if target_index <= source_index:
                    continue
                reverse_similarity = candidate_neighbors[target_index].get(source_index)
                if mutual_neighbors and reverse_similarity is None:
                    continue
                edge_weight = min(similarity, reverse_similarity) if reverse_similarity is not None else similarity
                graph.add_edge(source_index, target_index, weight=float(edge_weight))

    @staticmethod
    def _order_communities(communities: list[set[int]]) -> list[set[int]]:
        return sorted(
            communities,
            key=lambda community: (-len(community), min(community)),
        )

    @staticmethod
    def _top_candidate_indices(similarities: Any, *, neighbor_limit: int, np: Any) -> Any:
        if neighbor_limit >= len(similarities):
            return np.argsort(similarities)[::-1]
        candidate_indices = np.argpartition(similarities, -neighbor_limit)[-neighbor_limit:]
        return candidate_indices[np.argsort(similarities[candidate_indices])[::-1]]

    @staticmethod
    def _build_network_edges(graph: Any) -> list[tuple[int, int, float]]:
        return [
            (int(source), int(target), round(float(data.get("weight", 0.0)), 6))
            for source, target, data in sorted(graph.edges(data=True), key=lambda edge: (edge[0], edge[1]))
        ]
