from __future__ import annotations

import re

from app.services.topic_analysis_services.contracts import (
    AnalysisGroupRecord,
    TopicLabelEvidenceGroup,
)


class TopicLabelEvidenceBuilder:
    def __init__(self, *, max_groups: int, max_examples_per_group: int, max_terms_per_group: int, max_chars_per_example: int) -> None:
        self.max_groups = max_groups
        self.max_examples_per_group = max_examples_per_group
        self.max_terms_per_group = max_terms_per_group
        self.max_chars_per_example = max_chars_per_example

    def build_group_evidence(self, groups: list[AnalysisGroupRecord]) -> list[TopicLabelEvidenceGroup]:
        evidence_groups: list[TopicLabelEvidenceGroup] = []
        for group in groups:
            if len(evidence_groups) >= max(1, self.max_groups):
                break
            if group.is_noise:
                continue

            group_id = group.group_id.strip()
            if not group_id:
                continue

            evidence_groups.append(
                TopicLabelEvidenceGroup(
                    group_id=group_id,
                    current_label=group.label.strip(),
                    count=int(group.count),
                    share_percent=round(float(group.share) * 100, 1),
                    terms=self.collect_terms(group),
                    examples=self.collect_examples(group),
                )
            )
        return evidence_groups

    def collect_examples(self, group: AnalysisGroupRecord) -> list[str]:
        examples: list[str] = []
        max_examples = max(1, self.max_examples_per_group)
        max_chars = max(80, self.max_chars_per_example)
        for example in group.examples:
            text = str(example.source_text or example.text or "").strip()
            if not text:
                continue
            normalized = re.sub(r"\s+", " ", text)
            examples.append(normalized[:max_chars].rstrip())
            if len(examples) >= max_examples:
                break
        return examples

    def collect_terms(self, group: AnalysisGroupRecord) -> list[str]:
        terms: list[str] = []
        max_terms = max(1, self.max_terms_per_group)
        for term in group.terms:
            normalized = re.sub(r"\s+", " ", str(term).strip())
            if not normalized:
                continue
            terms.append(normalized)
            if len(terms) >= max_terms:
                break
        return terms
