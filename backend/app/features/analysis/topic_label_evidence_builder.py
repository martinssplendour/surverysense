from __future__ import annotations

import re
from collections import Counter

from app.features.analysis.topic_analysis_services.contracts import (
    AnalysisGroupRecord,
    TopicLabelEvidenceGroup,
)


class TopicLabelEvidenceBuilder:
    TOKEN_PATTERN = re.compile(r"[^\W_][^\W_'\-]*", re.UNICODE)
    MAX_CONTEXT_DOCUMENTS = 120
    LEADING_TRIM_WORDS = frozenset(
        {
            "a",
            "an",
            "and",
            "are",
            "as",
            "be",
            "been",
            "being",
            "but",
            "for",
            "from",
            "i",
            "in",
            "is",
            "it",
            "of",
            "on",
            "or",
            "our",
            "that",
            "the",
            "their",
            "these",
            "this",
            "those",
            "to",
            "was",
            "we",
            "were",
            "with",
            "you",
            "your",
        }
    )
    TRAILING_TRIM_WORDS = frozenset(
        {
            "a",
            "an",
            "and",
            "are",
            "as",
            "be",
            "been",
            "being",
            "but",
            "for",
            "from",
            "in",
            "is",
            "it",
            "of",
            "on",
            "or",
            "that",
            "the",
            "these",
            "this",
            "those",
            "to",
            "was",
            "were",
            "with",
        }
    )

    def __init__(self, *, max_groups: int, max_examples_per_group: int, max_terms_per_group: int, max_chars_per_example: int) -> None:
        self.max_groups = max_groups
        self.max_examples_per_group = max_examples_per_group
        self.max_terms_per_group = max_terms_per_group
        self.max_context_phrases_per_group = max(1, max_terms_per_group)
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
                    context_phrases=self.collect_context_phrases(group),
                    examples=self.collect_examples(group),
                )
            )
        return evidence_groups

    def collect_examples(self, group: AnalysisGroupRecord) -> list[str]:
        # Group documents are ordered before AI labeling. Use that order directly so
        # the naming evidence is the same response order users see in the modal.
        max_examples = max(1, self.max_examples_per_group)
        max_chars = max(80, self.max_chars_per_example)

        documents = list(group.documents) or list(group.examples)
        examples: list[str] = []
        for doc in documents:
            text = re.sub(r"\s+", " ", str(doc.text or "").strip())
            if not text:
                continue
            truncated = text[:max_chars].rstrip()
            examples.append(truncated)
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

    def collect_context_phrases(self, group: AnalysisGroupRecord) -> list[str]:
        # Count how many distinct documents each 2-3 gram appears in.
        # Document frequency (not term frequency) surfaces the cluster's characteristic
        # vocabulary without requiring exact term matches.
        doc_freq: Counter[str] = Counter()
        for text in self._collect_group_texts(group):
            tokens = self._tokenize(text)
            seen: set[str] = set()
            for n in (2, 3):
                for i in range(len(tokens) - n + 1):
                    phrase = self._trim_context_phrase(tokens[i : i + n])
                    if not phrase or len(phrase.split()) < 2:
                        continue
                    if phrase not in seen:
                        seen.add(phrase)
                        doc_freq[phrase] += 1

        selected: list[str] = []
        for phrase, count in doc_freq.most_common():
            if count < 2:
                break
            # skip if this phrase is a substring of (or contains) an already-selected one
            if any(phrase in existing or existing in phrase for existing in selected):
                continue
            selected.append(phrase)
            if len(selected) >= self.max_context_phrases_per_group:
                break
        return selected

    def _collect_group_texts(self, group: AnalysisGroupRecord) -> list[str]:
        texts: list[str] = []
        seen: set[str] = set()
        for document in group.documents:
            text = str(document.text or "").strip()
            key = text.casefold()
            if not text or key in seen:
                continue
            seen.add(key)
            texts.append(text)
            if len(texts) >= self.MAX_CONTEXT_DOCUMENTS:
                return texts

        for example in group.examples:
            text = str(example.source_text or example.text or "").strip()
            key = text.casefold()
            if not text or key in seen:
                continue
            seen.add(key)
            texts.append(text)
            if len(texts) >= self.MAX_CONTEXT_DOCUMENTS:
                break
        return texts

    def _trim_context_phrase(self, tokens: list[str]) -> str:
        start = 0
        end = len(tokens)
        while end - start > 1 and tokens[start] in self.LEADING_TRIM_WORDS:
            start += 1
        while end - start > 1 and tokens[end - 1] in self.TRAILING_TRIM_WORDS:
            end -= 1
        return " ".join(tokens[start:end]).strip()

    def _tokenize(self, text: str) -> list[str]:
        return [
            token.strip("-'").casefold()
            for token in self.TOKEN_PATTERN.findall(str(text))
            if len(token.strip("-'")) > 1
        ]
