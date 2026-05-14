from __future__ import annotations

import re
from collections.abc import Iterable

from app.features.analysis.topic_analysis_services.contracts import AnalysisGroupRecord


def compose_group_aliases(*alias_maps: dict[str, str]) -> dict[str, str]:
    combined: dict[str, str] = {}
    for alias_map in alias_maps:
        for source, target in alias_map.items():
            combined[str(source)] = str(target)

    def resolve(group_id: str) -> str:
        seen: set[str] = set()
        current = str(group_id)
        while current in combined and current not in seen:
            seen.add(current)
            next_group_id = combined[current]
            if next_group_id == current:
                break
            current = next_group_id
        return current

    return {source: resolve(target) for source, target in combined.items()}


def merge_unique_terms(terms: Iterable[str]) -> list[str]:
    merged_terms: list[str] = []
    seen: set[str] = set()
    for term in terms:
        normalized = re.sub(r"\s+", " ", str(term or "").strip())
        key = normalized.casefold()
        if not normalized or key in seen:
            continue
        seen.add(key)
        merged_terms.append(normalized)
    return merged_terms


def merge_term_strengths(groups: list[AnalysisGroupRecord], terms: list[str]) -> dict[str, float]:
    weighted_scores: dict[str, float] = {}
    for group in groups:
        weight = max(1, int(group.count or len(group.documents) or 1))
        for term, strength in group.term_strengths.items():
            key = str(term)
            weighted_scores[key] = weighted_scores.get(key, 0.0) + float(strength) * weight

    strongest_score = max([weighted_scores.get(term, 0.0) for term in terms] or [0.0])
    if strongest_score <= 0:
        return {}
    return {
        term: round(weighted_scores.get(term, 0.0) / strongest_score, 4)
        for term in terms
        if weighted_scores.get(term, 0.0) > 0
    }


def refresh_group_counts(groups: list[AnalysisGroupRecord]) -> None:
    total_documents = max(1, sum(len(group.documents) for group in groups))
    for group in groups:
        group.count = len(group.documents)
        group.share = round(group.count / total_documents, 4)
        group.total_documents = total_documents
    groups.sort(key=lambda group: (bool(group.is_noise), -int(group.count), str(group.group_id)))
