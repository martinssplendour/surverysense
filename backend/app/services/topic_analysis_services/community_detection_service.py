from __future__ import annotations

from importlib import metadata
from typing import Any

from app.core.exceptions import TopicAnalysisDependencyError
from app.services.topic_analysis_services.contracts import TopicModelRunResult


class CommunityDetectionAnalysisService:
    """Builds a similarity graph from embeddings and detects response communities."""

    def run(
        self,
        embeddings: Any,
        *,
        similarity_threshold: float,
        max_neighbors: int,
        resolution: float = 1.0,
        mutual_neighbors: bool = True,
    ) -> TopicModelRunResult:
        try:
            import networkx as nx
            import numpy as np
        except Exception as exc:  # pragma: no cover - dependency error path
            raise TopicAnalysisDependencyError(
                "networkx and numpy are required for community detection analysis."
            ) from exc

        embedding_array = np.asarray(embeddings, dtype=float)
        if embedding_array.ndim != 2:
            raise TopicAnalysisDependencyError("Community detection received invalid embedding data.")

        document_count = int(embedding_array.shape[0])
        if document_count == 0:
            return TopicModelRunResult(assignments=[], warnings=[])
        if document_count == 1:
            return TopicModelRunResult(
                assignments=[0],
                warnings=["Community detection found only one usable response, so it created one community."],
                layout_positions={0: (0.0, 0.0)},
            )

        warnings: list[str] = []
        cluster_embeddings = self._reduce_for_clustering(embedding_array, np, warnings=warnings)
        normalized_embeddings = self._normalize_rows(cluster_embeddings, np)
        graph = nx.Graph()
        graph.add_nodes_from(range(document_count))

        threshold = max(-1.0, min(1.0, float(similarity_threshold)))
        neighbor_limit = max(1, min(int(max_neighbors or 1), document_count - 1))

        candidate_neighbors = self._build_candidate_neighbors(
            normalized_embeddings,
            threshold=threshold,
            neighbor_limit=neighbor_limit,
            np=np,
        )
        self._add_similarity_edges(
            graph,
            candidate_neighbors=candidate_neighbors,
            mutual_neighbors=mutual_neighbors,
        )

        if graph.number_of_edges() == 0:
            warnings.append(
                "Community detection did not find responses above the similarity threshold, so each response is shown as its own community."
            )
            return TopicModelRunResult(
                assignments=list(range(document_count)),
                warnings=warnings,
                layout_positions=self._build_layout_positions(embedding_array, graph, nx, np),
            )

        ordered_communities, detector_warning = self._detect_communities(
            graph,
            document_count=document_count,
            resolution=resolution,
            nx=nx,
        )
        if detector_warning:
            warnings.append(detector_warning)

        assignments = [-1] * document_count
        singleton_count = 0
        for community_id, community in enumerate(ordered_communities):
            if len(community) == 1:
                singleton_count += 1
            for row_index in community:
                assignments[int(row_index)] = int(community_id)

        if singleton_count:
            warnings.append(
                f"Community detection placed {singleton_count} response(s) into single-response communities."
            )

        return TopicModelRunResult(
            assignments=assignments,
            warnings=warnings,
            network_edges=self._build_network_edges(graph),
            layout_positions=self._build_layout_positions(embedding_array, graph, nx, np),
        )

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
        neighbor_limit: int,
        np: Any,
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
                if similarity >= threshold:
                    row_neighbors[neighbor_index] = similarity
            candidate_neighbors.append(row_neighbors)
        return candidate_neighbors

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
    def _reduce_for_clustering(embedding_array: Any, np: Any, *, warnings: list[str] | None = None) -> Any:
        """UMAP reduction to 15 dims before graph construction.

        Only applied when the embedding space is high-dimensional enough to benefit
        (>15 dims) and the corpus is large enough for UMAP to be stable (>=10 docs).
        Falls back to raw embeddings if umap-learn is not installed.
        """
        n_docs, n_dims = int(embedding_array.shape[0]), int(embedding_array.shape[1])
        if n_docs < 10 or n_dims <= 15:
            return embedding_array
        if CommunityDetectionAnalysisService._has_incompatible_umap_runtime():
            if warnings is not None:
                warnings.append(
                    "UMAP clustering reduction was skipped because the installed umap-learn and scikit-learn versions are incompatible, so community detection used the original embeddings."
                )
            return embedding_array
        try:
            import umap as umap_lib
        except ImportError:  # pragma: no cover - optional dependency
            return embedding_array

        n_components = min(15, n_docs - 2)
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
            return reducer.fit_transform(embedding_array)
        except Exception:  # pragma: no cover - depends on optional dependency versions
            if warnings is not None:
                warnings.append(
                    "UMAP clustering reduction was skipped because dimensionality reduction failed, so community detection used the original embeddings."
            )
            return embedding_array

    @staticmethod
    def _has_incompatible_umap_runtime() -> bool:
        try:
            umap_version = metadata.version("umap-learn")
            sklearn_version = metadata.version("scikit-learn")
        except metadata.PackageNotFoundError:
            return False

        umap_major_minor = CommunityDetectionAnalysisService._major_minor_version(umap_version)
        sklearn_major_minor = CommunityDetectionAnalysisService._major_minor_version(sklearn_version)
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

    @staticmethod
    def _build_layout_positions(
        embedding_array: Any,
        graph: Any,
        nx: Any,
        np: Any,
    ) -> dict[int, tuple[float, float]]:
        """2D layout for scatter visualization.

        Uses UMAP when the corpus and embedding dimensions are large enough for it
        to produce a semantically meaningful layout. Falls back to NetworkX graph
        layout (circular when no edges, spring otherwise) for small or low-dim data.
        """
        n_docs, n_dims = int(embedding_array.shape[0]), int(embedding_array.shape[1])

        if (
            n_docs >= 4
            and n_dims > 2
            and not CommunityDetectionAnalysisService._has_incompatible_umap_runtime()
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
