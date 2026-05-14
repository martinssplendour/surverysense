from __future__ import annotations

import logging

from app.features.analysis.topic_analysis_services.config import TopicAnalysisConfig
from app.features.analysis.topic_analysis_services.contracts import AnalysisGroupRecord
from app.features.analysis.topic_analysis_services.group_post_processing_utils import (
    merge_term_strengths,
    merge_unique_terms,
    refresh_group_counts,
)

logger = logging.getLogger(__name__)


class TopicGroupTopTermMergeService:
    def __init__(self, *, config: TopicAnalysisConfig) -> None:
        self.config = config

    def merge(
        self,
        groups: list[AnalysisGroupRecord],
    ) -> tuple[list[AnalysisGroupRecord], dict[str, str]]:
        if not groups:
            logger.info("Top-term signature merge skipped: group_count=0.")
            return [], {}

        grouped_by_signature: dict[tuple[str, str], list[AnalysisGroupRecord]] = {}
        passthrough_groups: list[AnalysisGroupRecord] = []
        for group in groups:
            signature = self._top_term_signature(group)
            if group.is_noise or signature is None:
                passthrough_groups.append(group)
                continue
            grouped_by_signature.setdefault(signature, []).append(group)

        aliases: dict[str, str] = {}
        merged_groups: list[AnalysisGroupRecord] = list(passthrough_groups)
        for matching_groups in grouped_by_signature.values():
            matching_groups = sorted(
                matching_groups,
                key=lambda group: (-int(group.count or len(group.documents)), str(group.group_id)),
            )
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
                    is_noise=False,
                    documents=documents,
                    label_translation_warnings=[
                        warning
                        for group in matching_groups
                        for warning in group.label_translation_warnings
                    ],
                )
            )

        merged_signature_count = sum(1 for matching_groups in grouped_by_signature.values() if len(matching_groups) > 1)
        refresh_group_counts(merged_groups)
        logger.info(
            "Top-term signature merge details: signature_count=%s merged_signature_count=%s passthrough_group_count=%s output_group_count=%s.",
            len(grouped_by_signature),
            merged_signature_count,
            len(passthrough_groups),
            len(merged_groups),
        )
        return merged_groups, aliases

    @staticmethod
    def _top_term_signature(group: AnalysisGroupRecord) -> tuple[str, str] | None:
        ranked_terms = sorted(
            (
                (str(term), float(group.term_strengths.get(str(term), 0.0)), index)
                for index, term in enumerate(group.terms)
                if str(term).strip()
            ),
            key=lambda item: (-item[1], item[2], item[0]),
        )
        if len(ranked_terms) < 2:
            return None
        return tuple(sorted((ranked_terms[0][0].casefold(), ranked_terms[1][0].casefold())))
