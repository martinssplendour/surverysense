from __future__ import annotations

import re
from collections import Counter

from app.services.topic_analysis_services.contracts import (
    AnalysisGroupRecord,
    TopicLabelEvidenceGroup,
)


class TopicLabelEvidenceBuilder:
    TOKEN_PATTERN = re.compile(r"[^\W_][^\W_'\-]*", re.UNICODE)
    MAX_CONTEXT_DOCUMENTS = 120
    CONTEXT_QUALIFIERS = frozenset(
        {
            "too",
            "very",
            "really",
            "quite",
            "so",
            "more",
            "less",
            "not",
            "no",
            "never",
            "hard",
            "difficult",
            "easy",
            "easier",
            "clear",
            "clearer",
            "unclear",
            "confusing",
            "helpful",
            "unhelpful",
            "expensive",
            "cheaper",
            "affordable",
        }
    )
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

    def collect_context_phrases(self, group: AnalysisGroupRecord) -> list[str]:
        terms = self.collect_terms(group)
        term_tokens = [tokens for term in terms if (tokens := self._tokenize(term))]

        counts: Counter[str] = Counter()
        for text in self._collect_group_texts(group):
            tokens = self._tokenize(text)
            if not tokens:
                continue

            if term_tokens:
                for target_tokens in term_tokens:
                    target_length = len(target_tokens)
                    if len(tokens) < target_length:
                        continue

                    for index in range(0, len(tokens) - target_length + 1):
                        if tokens[index:index + target_length] != target_tokens:
                            continue
                        for phrase in self._context_phrase_candidates(tokens, index, target_length):
                            counts[phrase] += 1

            for phrase in self._qualifier_phrase_candidates(tokens):
                counts[phrase] += 1

        selected: list[str] = []
        for phrase, _count in sorted(counts.items(), key=self._context_phrase_sort_key):
            if phrase in selected:
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

    def _context_phrase_candidates(self, tokens: list[str], index: int, target_length: int) -> list[str]:
        candidates: list[str] = []
        start = max(0, index - 2)
        end = min(len(tokens), index + target_length + 2)
        candidates.append(self._trim_context_phrase(tokens[start:end]))

        if index > 0:
            candidates.append(self._trim_context_phrase(tokens[index - 1:index + target_length]))
        if index > 1:
            candidates.append(self._trim_context_phrase(tokens[index - 2:index + target_length]))
        if index + target_length < len(tokens):
            candidates.append(self._trim_context_phrase(tokens[index:index + target_length + 1]))

        cleaned: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            if not candidate:
                continue
            if candidate in seen:
                continue
            seen.add(candidate)
            cleaned.append(candidate)
        return cleaned

    def _qualifier_phrase_candidates(self, tokens: list[str]) -> list[str]:
        candidates: list[str] = []
        seen: set[str] = set()
        for index, token in enumerate(tokens):
            if token not in self.CONTEXT_QUALIFIERS:
                continue
            max_end = min(len(tokens), index + 4)
            for end in range(index + 2, max_end + 1):
                candidate = self._trim_context_phrase(tokens[index:end])
                if not candidate or candidate in seen:
                    continue
                if len(candidate.split()) < 2:
                    continue
                seen.add(candidate)
                candidates.append(candidate)
        return candidates

    def _trim_context_phrase(self, tokens: list[str]) -> str:
        start = 0
        end = len(tokens)
        while end - start > 1 and tokens[start] in self.LEADING_TRIM_WORDS:
            start += 1
        while end - start > 1 and tokens[end - 1] in self.TRAILING_TRIM_WORDS:
            end -= 1
        return " ".join(tokens[start:end]).strip()

    def _context_phrase_sort_key(self, item: tuple[str, int]) -> tuple[int, int, int, str]:
        phrase, count = item
        tokens = phrase.split()
        qualifier_score = sum(1 for token in tokens if token in self.CONTEXT_QUALIFIERS)
        return (-int(count), -qualifier_score, len(tokens), phrase)

    def _tokenize(self, text: str) -> list[str]:
        return [
            token.strip("-'").casefold()
            for token in self.TOKEN_PATTERN.findall(str(text))
            if len(token.strip("-'")) > 1
        ]
