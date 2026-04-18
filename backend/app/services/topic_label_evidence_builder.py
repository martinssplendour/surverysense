from __future__ import annotations

import re


class TopicLabelEvidenceBuilder:
    def __init__(self, *, max_groups: int, max_examples_per_group: int, max_terms_per_group: int, max_chars_per_example: int) -> None:
        self.max_groups = max_groups
        self.max_examples_per_group = max_examples_per_group
        self.max_terms_per_group = max_terms_per_group
        self.max_chars_per_example = max_chars_per_example

    def build_group_evidence(self, groups: list[dict[str, object]]) -> list[dict[str, object]]:
        evidence_groups: list[dict[str, object]] = []
        for group in groups:
            if len(evidence_groups) >= max(1, self.max_groups):
                break
            if bool(group.get("is_noise")):
                continue

            group_id = str(group.get("group_id", "")).strip()
            if not group_id:
                continue

            evidence_groups.append(
                {
                    "group_id": group_id,
                    "current_label": str(group.get("label", "")).strip(),
                    "count": int(group.get("count", 0)),
                    "share_percent": round(float(group.get("share", 0.0)) * 100, 1),
                    "terms": self.collect_terms(group),
                    "examples": self.collect_examples(group),
                }
            )
        return evidence_groups

    def collect_examples(self, group: dict[str, object]) -> list[str]:
        examples: list[str] = []
        max_examples = max(1, self.max_examples_per_group)
        max_chars = max(80, self.max_chars_per_example)
        for example in group.get("examples", []):
            if not isinstance(example, dict):
                continue
            text = str(example.get("source_text") or example.get("text") or "").strip()
            if not text:
                continue
            normalized = re.sub(r"\s+", " ", text)
            examples.append(normalized[:max_chars].rstrip())
            if len(examples) >= max_examples:
                break
        return examples

    def collect_terms(self, group: dict[str, object]) -> list[str]:
        terms: list[str] = []
        max_terms = max(1, self.max_terms_per_group)
        for term in group.get("terms", []):
            normalized = re.sub(r"\s+", " ", str(term).strip())
            if not normalized:
                continue
            terms.append(normalized)
            if len(terms) >= max_terms:
                break
        return terms
