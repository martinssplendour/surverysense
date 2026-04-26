from __future__ import annotations

import re
from collections import defaultdict

from app.features.analysis.topic_analysis_services.config import (
    PreparedDocument,
    TopicAnalysisConfig,
)
from app.features.analysis.topic_analysis_services.contracts import (
    AnalysisDocumentRecord,
    AnalysisGroupRecord,
    TopicModelGroupDefinition,
)
from app.features.analysis.topic_analysis_services.example_selection_service import (
    RepresentativeExampleSelectionService,
)
from app.features.analysis.topic_analysis_services.keyword_service import (
    TopicAnalysisKeywordService,
)
from app.features.analysis.topic_analysis_services.narrative_service import (
    TopicAnalysisNarrativeService,
)
from app.features.common.protocols import TranslationServiceProtocol
from app.models.enums import AnalysisModelKey


class TopicGroupAssemblyService:
    def __init__(
        self,
        *,
        config: TopicAnalysisConfig,
        keyword_service: TopicAnalysisKeywordService,
        narrative_service: TopicAnalysisNarrativeService,
        representative_example_service: RepresentativeExampleSelectionService,
        translation_service: TranslationServiceProtocol | None = None,
    ) -> None:
        self.config = config
        self.keyword_service = keyword_service
        self.narrative_service = narrative_service
        self.representative_example_service = representative_example_service
        self.translation_service = translation_service

    def build_groups(
        self,
        *,
        documents: list[PreparedDocument],
        assignments: list[int],
        explicit_groups: dict[str, TopicModelGroupDefinition],
        network_edges: list[tuple[int, int, float]] | None = None,
        model_key: str,
    ) -> list[AnalysisGroupRecord]:
        grouped_documents: dict[int, list[tuple[int, PreparedDocument]]] = defaultdict(list)
        for node_index, (assignment, document) in enumerate(zip(assignments, documents)):
            grouped_documents[int(assignment)].append((int(node_index), document))

        total_documents = max(1, len(documents))
        groups: list[AnalysisGroupRecord] = []
        ordered_group_ids = sorted(
            grouped_documents.keys(),
            key=lambda group_id: (-len(grouped_documents[group_id]), group_id),
        )
        edge_scores = self._build_edge_scores_by_group(
            assignments=assignments,
            network_edges=network_edges or [],
        )

        if model_key == AnalysisModelKey.COMMUNITY.value:
            fallback_prefix = "Community"
            prefer_terms = False
        else:
            fallback_prefix = "Group"
            prefer_terms = False

        for group_id in ordered_group_ids:
            group_key = str(group_id)
            grouped_entries = grouped_documents[group_id]
            grouped_rows = [document for _node_index, document in grouped_entries]
            grouped_texts = [document.text for document in grouped_rows]
            explicit_group = explicit_groups.get(group_key, TopicModelGroupDefinition())
            terms = [str(term) for term in explicit_group.terms if term.strip()]
            terms = self.keyword_service.sanitize_terms(terms, top_n=self.config.top_terms_per_group)
            if not terms:
                terms = self.keyword_service.top_terms(grouped_texts, top_n=self.config.top_terms_per_group)
            ordered_grouped_entries = self._order_documents_by_representativeness(
                grouped_entries,
                terms=terms,
                edge_scores=edge_scores.get(int(group_id), {}),
            )
            ordered_grouped_rows = [document for _node_index, document in ordered_grouped_entries]

            is_noise = bool(explicit_group.is_noise or group_id == -1)
            label = self.narrative_service.build_label(
                texts=grouped_texts,
                terms=terms,
                is_noise=is_noise,
                fallback_prefix=fallback_prefix,
                fallback_id=group_key,
                prefer_terms=prefer_terms,
            )
            examples = self.representative_example_service.select(
                grouped_rows,
                terms=terms,
                max_examples=self.config.representative_examples_per_group,
            )
            comment = self.narrative_service.build_comment(
                label=label,
                count=int(len(grouped_rows)),
                total_documents=total_documents,
                examples=examples,
            )
            groups.append(
                AnalysisGroupRecord(
                    group_id=group_key,
                    label=label,
                    comment=comment,
                    count=int(len(grouped_rows)),
                    share=round(len(grouped_rows) / total_documents, 4),
                    total_documents=total_documents,
                    terms=list(terms),
                    examples=examples,
                    is_noise=is_noise,
                    documents=[
                        AnalysisDocumentRecord(
                            row_number=int(document.row_number),
                            text=document.text,
                        )
                        for document in ordered_grouped_rows
                        if int(document.row_number) > 0 and document.text
                    ],
                )
            )

        return groups

    @classmethod
    def _order_documents_by_term_evidence(
        cls,
        documents: list[PreparedDocument],
        *,
        terms: list[str],
    ) -> list[PreparedDocument]:
        ordered_entries = cls._order_documents_by_representativeness(
            [(index, document) for index, document in enumerate(documents)],
            terms=terms,
            edge_scores={},
        )
        return [document for _node_index, document in ordered_entries]

    @classmethod
    def _order_documents_by_representativeness(
        cls,
        documents: list[tuple[int, PreparedDocument]],
        *,
        terms: list[str],
        edge_scores: dict[int, tuple[float, int]],
    ) -> list[tuple[int, PreparedDocument]]:
        if not documents:
            return list(documents)

        weighted_patterns = [
            (index, term, cls._compile_term_pattern(term))
            for index, term in enumerate(terms)
            if term.strip()
        ]

        scored_documents: list[tuple[tuple[float | int, ...], tuple[int, PreparedDocument]]] = []
        for original_index, (node_index, document) in enumerate(documents):
            weighted_degree, neighbor_count = edge_scores.get(int(node_index), (0.0, 0))
            term_score = cls._score_term_evidence(document.text or "", weighted_patterns)
            score = (
                round(float(weighted_degree), 6),
                int(neighbor_count),
                *term_score,
                -original_index,
            )
            scored_documents.append((score, (node_index, document)))

        scored_documents.sort(key=lambda item: item[0], reverse=True)
        return [document for _score, document in scored_documents]

    @classmethod
    def _score_term_evidence(
        cls,
        text: str,
        weighted_patterns: list[tuple[int, str, re.Pattern[str]]],
    ) -> tuple[int, int, int, int, int, float, int]:
        if not weighted_patterns:
            return (0, 0, 0, 0, 0, 0.0, 0)

        total_matches = 0
        unique_hits = 0
        weighted_hits = 0
        best_term_index = len(weighted_patterns)
        first_position = len(text) + 1
        for index, _term, pattern in weighted_patterns:
            matches = list(pattern.finditer(text))
            if not matches:
                continue
            unique_hits += 1
            best_term_index = min(best_term_index, index)
            match_count = len(matches)
            total_matches += match_count
            weighted_hits += match_count * (len(weighted_patterns) - index)
            first_position = min(first_position, matches[0].start())

        if not unique_hits:
            return (0, 0, 0, 0, 0, 0.0, 0)

        length_target = abs(len(text) - 220)
        return (
            1,
            -best_term_index,
            weighted_hits,
            unique_hits,
            total_matches,
            -float(length_target),
            -first_position,
        )

    @staticmethod
    def _build_edge_scores_by_group(
        *,
        assignments: list[int],
        network_edges: list[tuple[int, int, float]],
    ) -> dict[int, dict[int, tuple[float, int]]]:
        grouped_scores: dict[int, dict[int, list[float]]] = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
        assignment_count = len(assignments)
        for source_index, target_index, weight in network_edges:
            source = int(source_index)
            target = int(target_index)
            if source < 0 or target < 0 or source >= assignment_count or target >= assignment_count:
                continue
            source_group = int(assignments[source])
            if source_group != int(assignments[target]):
                continue
            edge_weight = max(0.0, float(weight))
            grouped_scores[source_group][source][0] += edge_weight
            grouped_scores[source_group][source][1] += 1.0
            grouped_scores[source_group][target][0] += edge_weight
            grouped_scores[source_group][target][1] += 1.0

        return {
            group_id: {
                node_index: (float(values[0]), int(values[1]))
                for node_index, values in node_scores.items()
            }
            for group_id, node_scores in grouped_scores.items()
        }

    @staticmethod
    def _compile_term_pattern(term: str) -> re.Pattern[str]:
        escaped = re.escape(term.strip())
        escaped = escaped.replace(r"\ ", r"\s+")
        return re.compile(rf"(?<!\w){escaped}(?!\w)", re.IGNORECASE | re.UNICODE)
