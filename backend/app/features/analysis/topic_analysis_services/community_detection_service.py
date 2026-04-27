from __future__ import annotations

from importlib import metadata
from typing import Any

from app.core.exceptions import TopicAnalysisDependencyError
from app.features.analysis.topic_analysis_services.contracts import (
    TopicModelGroupDefinition,
    TopicModelRunResult,
)


class CommunityDetectionAnalysisService:
    """Builds a similarity graph from embeddings and detects response communities."""

    LANGUAGE_EDGE_THRESHOLD_LIFT = 0.08
    LANGUAGE_SPLIT_THRESHOLD_LIFT = 0.06
    MIN_LANGUAGE_EDGE_THRESHOLD = 0.78
    LANGUAGE_DOMINANCE_SHARE = 0.75
    MIN_LANGUAGE_GUARD_COMMUNITY_SIZE = 4
    NOISE_GROUP_ID = -1
    MIN_TOPIC_COMMUNITY_SIZE = 3
    MIN_TOPIC_SAMPLE_SIZE_FOR_SIZE_RULE = 5

    def run(
        self,
        embeddings: Any,
        *,
        similarity_threshold: float,
        max_neighbors: int,
        resolution: float = 1.0,
        mutual_neighbors: bool = True,
        languages: list[str | None] | None = None,
    ) -> TopicModelRunResult:
        try:
            import networkx as nx
            import numpy as np
        except Exception as exc:  # pragma: no cover - dependency error path
            raise TopicAnalysisDependencyError(
                "networkx and numpy are required for community detection analysis."
            ) from exc

        embedding_array = np.asarray(embeddings, dtype=np.float32)
        if embedding_array.ndim != 2:
            raise TopicAnalysisDependencyError("Community detection received invalid embedding data.")

        document_count = int(embedding_array.shape[0])
        if document_count == 0:
            return TopicModelRunResult(assignments=[], warnings=[])
        if document_count == 1:
            return TopicModelRunResult(
                assignments=[self.NOISE_GROUP_ID],
                warnings=["Community detection found only one usable response, so it marked it as unassigned noise."],
                groups={str(self.NOISE_GROUP_ID): TopicModelGroupDefinition(is_noise=True)},
                layout_positions={0: (0.0, 0.0)},
            )

        warnings: list[str] = []
        cluster_embeddings, used_reduction = self._reduce_for_clustering(embedding_array, np, warnings=warnings)
        normalized_embeddings = self._normalize_rows(cluster_embeddings, np)
        graph = nx.Graph()
        graph.add_nodes_from(range(document_count))

        threshold = max(-1.0, min(1.0, float(similarity_threshold)))
        language_edge_threshold = self._language_edge_threshold(threshold)
        normalized_languages = self._normalize_languages(languages, document_count=document_count)
        language_guard_active = self._has_non_english_languages(normalized_languages)
        neighbor_limit = max(1, min(int(max_neighbors or 1), document_count - 1))

        candidate_neighbors = self._build_candidate_neighbors(
            normalized_embeddings,
            threshold=threshold,
            language_edge_threshold=language_edge_threshold,
            neighbor_limit=neighbor_limit,
            np=np,
            languages=normalized_languages,
        )
        self._add_similarity_edges(
            graph,
            candidate_neighbors=candidate_neighbors,
            mutual_neighbors=mutual_neighbors,
        )

        if language_guard_active:
            warnings.append(
                "Community detection used stricter same-language similarity checks for non-English responses to reduce language-only clusters."
            )

        if graph.number_of_edges() == 0:
            warnings.append(
                "Community detection did not find responses above the similarity threshold, so all responses were marked as unassigned noise."
            )
            return TopicModelRunResult(
                assignments=[self.NOISE_GROUP_ID for _index in range(document_count)],
                warnings=warnings,
                groups={str(self.NOISE_GROUP_ID): TopicModelGroupDefinition(is_noise=True)},
                layout_positions=self._build_layout_positions(
                    embedding_array,
                    graph,
                    nx,
                    np,
                    reduced_embeddings=cluster_embeddings if used_reduction else None,
                ),
            )

        ordered_communities, detector_warning = self._detect_communities(
            graph,
            document_count=document_count,
            resolution=resolution,
            nx=nx,
        )
        if detector_warning:
            warnings.append(detector_warning)

        ordered_communities, split_count = self._split_language_dominant_communities(
            ordered_communities,
            graph=graph,
            languages=normalized_languages,
            language_split_threshold=self._language_split_threshold(language_edge_threshold),
            nx=nx,
        )
        if split_count:
            warnings.append(
                f"Community detection split {split_count} language-dominant communit{'y' if split_count == 1 else 'ies'} with stricter topical similarity so language-only groups are not treated as topics."
            )

        assignments, explicit_groups, noise_response_count = self._assign_communities_with_noise(
            ordered_communities,
            document_count=document_count,
        )
        if noise_response_count:
            warnings.append(
                f"Community detection marked {noise_response_count} weakly connected response(s) as unassigned noise."
            )

        return TopicModelRunResult(
            assignments=assignments,
            warnings=warnings,
            groups=explicit_groups,
            network_edges=self._build_network_edges(graph),
            layout_positions=self._build_layout_positions(
                embedding_array,
                graph,
                nx,
                np,
                reduced_embeddings=cluster_embeddings if used_reduction else None,
            ),
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
    def _split_language_dominant_communities(
        cls,
        communities: list[set[int]],
        *,
        graph: Any,
        languages: list[str | None],
        language_split_threshold: float,
        nx: Any,
    ) -> tuple[list[set[int]], int]:
        if not cls._has_non_english_languages(languages):
            return communities, 0

        refined_communities: list[set[int]] = []
        split_count = 0
        for community in communities:
            dominant_language = cls._dominant_non_english_language(community, languages)
            if dominant_language is None:
                refined_communities.append(community)
                continue

            strong_subgraph = nx.Graph()
            strong_subgraph.add_nodes_from(community)
            for source, target, data in graph.subgraph(community).edges(data=True):
                if float(data.get("weight", 0.0)) >= language_split_threshold:
                    strong_subgraph.add_edge(source, target, weight=float(data.get("weight", 0.0)))

            components = [set(component) for component in nx.connected_components(strong_subgraph)]
            if len(components) > 1:
                split_count += 1
                refined_communities.extend(components)
            else:
                refined_communities.append(community)

        return cls._order_communities(refined_communities), split_count

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

    @classmethod
    def _dominant_non_english_language(cls, community: set[int], languages: list[str | None]) -> str | None:
        if len(community) < cls.MIN_LANGUAGE_GUARD_COMMUNITY_SIZE:
            return None

        counts: dict[str, int] = {}
        for node_index in community:
            language = languages[int(node_index)] if int(node_index) < len(languages) else None
            if not language or language == "en":
                continue
            counts[language] = counts.get(language, 0) + 1
        if not counts:
            return None

        language, count = max(counts.items(), key=lambda item: item[1])
        if count / max(1, len(community)) < cls.LANGUAGE_DOMINANCE_SHARE:
            return None
        return language

    @classmethod
    def _pair_similarity_threshold(
        cls,
        *,
        source_index: int,
        target_index: int,
        base_threshold: float,
        language_edge_threshold: float,
        languages: list[str | None] | None,
    ) -> float:
        if cls._same_non_english_language(source_index, target_index, languages):
            return language_edge_threshold
        return base_threshold

    @classmethod
    def _language_edge_threshold(cls, base_threshold: float) -> float:
        return min(0.98, max(float(base_threshold) + cls.LANGUAGE_EDGE_THRESHOLD_LIFT, cls.MIN_LANGUAGE_EDGE_THRESHOLD))

    @classmethod
    def _language_split_threshold(cls, language_edge_threshold: float) -> float:
        return min(0.98, float(language_edge_threshold) + cls.LANGUAGE_SPLIT_THRESHOLD_LIFT)

    @staticmethod
    def _same_non_english_language(
        source_index: int,
        target_index: int,
        languages: list[str | None] | None,
    ) -> bool:
        if not languages:
            return False
        if source_index >= len(languages) or target_index >= len(languages):
            return False
        source_language = languages[source_index]
        target_language = languages[target_index]
        return bool(source_language and source_language == target_language and source_language != "en")

    @staticmethod
    def _normalize_languages(languages: list[str | None] | None, *, document_count: int) -> list[str | None]:
        normalized: list[str | None] = []
        for language in list(languages or [])[:document_count]:
            value = str(language or "").strip().casefold()
            normalized.append(value if value and value != "auto" else None)
        if len(normalized) < document_count:
            normalized.extend([None] * (document_count - len(normalized)))
        return normalized

    @staticmethod
    def _has_non_english_languages(languages: list[str | None]) -> bool:
        return any(language and language != "en" for language in languages)

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
    def _reduce_for_clustering(embedding_array: Any, np: Any, *, warnings: list[str] | None = None) -> tuple[Any, bool]:
        """UMAP reduction to 15 dims before graph construction.

        Only applied when the embedding space is high-dimensional enough to benefit
        (>15 dims) and the corpus is large enough for UMAP to be stable (>=10 docs).
        Falls back to raw embeddings if umap-learn is not installed.
        """
        n_docs, n_dims = int(embedding_array.shape[0]), int(embedding_array.shape[1])
        if n_docs < 10 or n_dims <= 15:
            return embedding_array, False
        if CommunityDetectionAnalysisService._has_incompatible_umap_runtime():
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
    def _positions_from_reduced_embeddings(reduced_embeddings: Any, np: Any) -> dict[int, tuple[float, float]]:
        reduced_array = np.asarray(reduced_embeddings, dtype=np.float32)
        if reduced_array.ndim != 2 or int(reduced_array.shape[0]) == 0 or int(reduced_array.shape[1]) < 2:
            return {}
        return {
            i: (round(float(reduced_array[i, 0]), 6), round(float(reduced_array[i, 1]), 6))
            for i in range(int(reduced_array.shape[0]))
        }

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
