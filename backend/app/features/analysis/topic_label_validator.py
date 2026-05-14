from __future__ import annotations

import re

from app.features.analysis.topic_analysis_services.contracts import TopicLabelEvidenceGroup


class TopicLabelValidator:
    GENERIC_LABELS = frozenset(
        {
            "feedback",
            "general feedback",
            "general responses",
            "general topics",
            "misc",
            "miscellaneous",
            "mixed",
            "mixed feedback",
            "other",
            "other feedback",
            "other responses",
            "responses",
            "survey feedback",
            "topic",
            "topics",
            "uncategorized",
            "unclear",
            "unclear feedback",
            "unclear responses",
            "unknown",
        }
    )
    PLACEHOLDER_TOKENS = frozenset(
        {
            "abc",
            "blah",
            "example",
            "foo",
            "ipsum",
            "lorem",
            "placeholder",
            "sample",
            "test",
            "todo",
            "tbd",
            "xxx",
        }
    )
    LABEL_TOKEN_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)

    def is_valid_ai_label(self, label: str, group: TopicLabelEvidenceGroup) -> bool:
        normalized = self.normalize_for_validation(label)
        tokens = self.label_tokens(label)
        if not normalized or not tokens:
            return False
        if normalized in self.GENERIC_LABELS:
            return False
        if any(token in self.PLACEHOLDER_TOKENS for token in tokens):
            return False
        if self.has_excessive_repetition(tokens):
            return False
        if self.is_keyword_stitch_label(tokens):
            return False
        if not self.has_reasonable_length(label, tokens):
            return False
        if self.is_unsupported_generic_label(tokens, group):
            return False
        return True

    @classmethod
    def is_keyword_stitch_label(cls, tokens: list[str]) -> bool:
        if len(tokens) < 3:
            return False
        if {"printed", "bound", "teacher"}.issubset(set(tokens)):
            return True
        return False

    @classmethod
    def has_reasonable_length(cls, label: str, tokens: list[str]) -> bool:
        if len(tokens) < 3 or len(tokens) > 8:
            return False
        stripped = label.strip()
        return 4 <= len(stripped) <= 80

    @staticmethod
    def has_excessive_repetition(tokens: list[str]) -> bool:
        unique_tokens = set(tokens)
        if len(unique_tokens) == 1 and len(tokens) > 1:
            return True
        if len(tokens) >= 4 and len(unique_tokens) <= 2:
            return True
        return False

    def is_unsupported_generic_label(self, tokens: list[str], group: TopicLabelEvidenceGroup) -> bool:
        evidence_tokens = self.evidence_tokens(group)
        if not evidence_tokens:
            return False
        content_tokens = [token for token in tokens if token not in self.GENERIC_LABELS]
        if not content_tokens:
            return True
        matching_tokens = [token for token in content_tokens if token in evidence_tokens]
        return not matching_tokens and len(content_tokens) <= 2

    def evidence_tokens(self, group: TopicLabelEvidenceGroup) -> set[str]:
        ngram_terms = [
            item.term
            for item in [*group.top_unigrams, *group.top_bigrams, *group.top_trigrams]
        ]
        ngram_documents = [
            document
            for item in [*group.top_bigrams, *group.top_trigrams]
            for document in item.documents
        ]
        evidence_parts = [
            *group.terms,
            *group.context_phrases,
            *ngram_terms,
            *ngram_documents,
            *group.tightest_responses,
        ]
        return {
            token
            for part in evidence_parts
            for token in self.label_tokens(part)
            if len(token) > 2
        }

    @classmethod
    def label_tokens(cls, label: str) -> list[str]:
        return [token.casefold() for token in cls.LABEL_TOKEN_PATTERN.findall(str(label or ""))]

    @classmethod
    def normalize_for_validation(cls, label: str) -> str:
        return " ".join(cls.label_tokens(label))
