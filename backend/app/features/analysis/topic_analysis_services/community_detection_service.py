from __future__ import annotations

from typing import Any

from app.core.exceptions import TopicAnalysisDependencyError
from app.features.analysis.topic_analysis_services.community_graph import CommunityGraphMixin
from app.features.analysis.topic_analysis_services.community_language import CommunityLanguageGuardMixin
from app.features.analysis.topic_analysis_services.community_layout import CommunityLayoutMixin
from app.features.analysis.topic_analysis_services.contracts import (
    TopicModelGroupDefinition,
    TopicModelRunResult,
)


class CommunityDetectionAnalysisService(
    CommunityLanguageGuardMixin,
    CommunityLayoutMixin,
    CommunityGraphMixin,
):
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
        normalized_embeddings = self._normalize_rows(embedding_array, np)
        candidate_embeddings = self._build_candidate_projection(embedding_array, np, warnings=warnings)
        normalized_candidate_embeddings = self._normalize_rows(candidate_embeddings, np)
        graph = nx.Graph()
        graph.add_nodes_from(range(document_count))

        threshold = max(-1.0, min(1.0, float(similarity_threshold)))
        language_edge_threshold = self._language_edge_threshold(threshold)
        normalized_languages = self._normalize_languages(languages, document_count=document_count)
        language_guard_active = self._has_non_english_languages(normalized_languages)
        neighbor_limit = max(1, min(int(max_neighbors or 1), document_count - 1))

        candidate_neighbors = self._build_candidate_neighbors(
            normalized_candidate_embeddings,
            normalized_verification_embeddings=normalized_embeddings,
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
            ),
        )
