"""Language-aware community detection guards."""
from __future__ import annotations

from typing import Any


class CommunityLanguageGuardMixin:
    """Helpers that prevent language-only clusters from being treated as topics."""

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
