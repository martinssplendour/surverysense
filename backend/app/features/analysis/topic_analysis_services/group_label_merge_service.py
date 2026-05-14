from __future__ import annotations

import logging
import re

from app.features.analysis.topic_analysis_services.config import TopicAnalysisConfig
from app.features.analysis.topic_analysis_services.contracts import AnalysisGroupRecord
from app.features.analysis.topic_analysis_services.group_post_processing_utils import (
    merge_term_strengths,
    merge_unique_terms,
)
from app.features.analysis.topic_analysis_services.narrative_service import TopicAnalysisNarrativeService
from app.features.common.document_relevance import DocumentRelevanceSorter

logger = logging.getLogger(__name__)


class TopicGroupLabelMergeService:
    def __init__(
        self,
        *,
        config: TopicAnalysisConfig,
        narrative_service: TopicAnalysisNarrativeService,
    ) -> None:
        self.config = config
        self.narrative_service = narrative_service

    def merge(
        self,
        groups: list[AnalysisGroupRecord],
    ) -> tuple[list[AnalysisGroupRecord], dict[str, str]]:
        if not groups:
            logger.info("Label merge skipped: group_count=0.")
            return [], {}

        aliases: dict[str, str] = {}
        merged_groups: list[AnalysisGroupRecord] = []
        for matching_groups in self._group_by_matching_labels(groups):
            primary = matching_groups[0]
            primary_id = str(primary.group_id)
            for group in matching_groups:
                aliases[str(group.group_id)] = primary_id

            if len(matching_groups) == 1:
                merged_groups.append(primary)
                continue

            documents = [
                document
                for group in matching_groups
                for document in group.documents
            ]
            examples = [
                example
                for group in matching_groups
                for example in group.examples
            ]
            terms = merge_unique_terms(
                term
                for group in matching_groups
                for term in group.terms
            )
            count = sum(int(group.count or len(group.documents)) for group in matching_groups)

            merged_groups.append(
                AnalysisGroupRecord(
                    group_id=primary_id,
                    label=primary.label,
                    source_label=primary.source_label,
                    translated=any(group.translated for group in matching_groups),
                    ai_generated=any(group.ai_generated for group in matching_groups),
                    count=count,
                    share=0.0,
                    total_documents=0,
                    terms=terms,
                    term_strengths=merge_term_strengths(matching_groups, terms),
                    examples=examples[: self.config.representative_examples_per_group],
                    is_noise=primary.is_noise,
                    documents=documents,
                    label_translation_warnings=[
                        warning
                        for group in matching_groups
                        for warning in group.label_translation_warnings
                    ],
                )
            )

        total_documents = max(1, sum(int(group.count or len(group.documents)) for group in merged_groups))
        for group in merged_groups:
            group.count = int(group.count or len(group.documents))
            group.share = round(group.count / total_documents, 4)
            group.total_documents = total_documents
            group.comment = self.narrative_service.build_comment(
                label=group.label or "Group",
                count=group.count,
                total_documents=total_documents,
                examples=list(group.examples),
            )

        merged_groups.sort(key=lambda group: (-int(group.count), str(group.group_id)))
        logger.info(
            "Label merge details: input_group_count=%s output_group_count=%s merged_group_count=%s.",
            len(groups),
            len(merged_groups),
            sum(1 for source, target in aliases.items() if source != target),
        )
        return merged_groups, aliases

    def _group_by_matching_labels(self, groups: list[AnalysisGroupRecord]) -> list[list[AnalysisGroupRecord]]:
        parents = list(range(len(groups)))

        def find(index: int) -> int:
            while parents[index] != index:
                parents[index] = parents[parents[index]]
                index = parents[index]
            return index

        def union(left: int, right: int) -> None:
            left_root = find(left)
            right_root = find(right)
            if left_root != right_root:
                parents[right_root] = left_root

        exact_label_indexes: dict[tuple[bool, str], int] = {}
        ngram_indexes: dict[tuple[bool, str], int] = {}
        for index, group in enumerate(groups):
            is_noise = bool(group.is_noise)
            normalized_label = self._normalize_group_label(group.label)
            exact_label = normalized_label or str(group.group_id).strip()
            exact_key = (is_noise, exact_label)
            if exact_key in exact_label_indexes:
                union(exact_label_indexes[exact_key], index)
            else:
                exact_label_indexes[exact_key] = index

            for label_ngram in self._label_merge_ngrams(normalized_label):
                ngram_key = (is_noise, label_ngram)
                if ngram_key in ngram_indexes:
                    union(ngram_indexes[ngram_key], index)
                else:
                    ngram_indexes[ngram_key] = index

        grouped: dict[int, list[AnalysisGroupRecord]] = {}
        for index, group in enumerate(groups):
            grouped.setdefault(find(index), []).append(group)
        return list(grouped.values())

    @classmethod
    def _label_merge_ngrams(cls, label: str) -> set[str]:
        tokens = cls._label_merge_tokens(label)
        ngrams: set[str] = set()
        for ngram_size in (2, 3):
            for index in range(0, len(tokens) - ngram_size + 1):
                ngrams.add(" ".join(tokens[index:index + ngram_size]))
        return ngrams

    @staticmethod
    def _label_merge_tokens(label: str) -> list[str]:
        stopwords = set(DocumentRelevanceSorter.STOPWORDS) - {"too"}
        return [
            token.casefold()
            for token in DocumentRelevanceSorter.TOKEN_PATTERN.findall(str(label or ""))
            if len(token) > 2 and token.casefold() not in stopwords
        ]

    @staticmethod
    def _normalize_group_label(label: str) -> str:
        return re.sub(r"\s+", " ", str(label or "").strip().casefold())
