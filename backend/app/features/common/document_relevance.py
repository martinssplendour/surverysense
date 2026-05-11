from __future__ import annotations

import re
from typing import Protocol, TypeVar


class TextRecordProtocol(Protocol):
    text: str


TextRecordT = TypeVar("TextRecordT", bound=TextRecordProtocol)


class DocumentRelevanceSorter:
    TOKEN_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)
    STOPWORDS = frozenset(
        {
            "a",
            "an",
            "and",
            "are",
            "as",
            "at",
            "be",
            "but",
            "by",
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
            "so",
            "that",
            "the",
            "their",
            "this",
            "to",
            "too",
            "we",
            "with",
        }
    )

    @classmethod
    def order_by_label_and_terms(
        cls,
        records: list[TextRecordT],
        *,
        label: str,
        terms: list[str],
    ) -> list[TextRecordT]:
        relevance_tokens = cls.build_relevance_tokens(label, terms[:4])
        if not records or not relevance_tokens:
            return list(records)

        scored_records: list[tuple[tuple[int, int, int, int], TextRecordT]] = []
        for original_index, record in enumerate(records):
            text = str(record.text or "")
            document_tokens = cls.tokenize(text)
            overlap_count = len(document_tokens & relevance_tokens)
            word_count = len(cls.TOKEN_PATTERN.findall(text))
            score = (-overlap_count, word_count, len(text), original_index)
            scored_records.append((score, record))

        scored_records.sort(key=lambda item: item[0])
        return [record for _score, record in scored_records]

    @classmethod
    def build_relevance_tokens(cls, label: str, terms: list[str]) -> set[str]:
        tokens: set[str] = set()
        for value in [label, *terms]:
            tokens.update(cls.tokenize(str(value or "")))
        return tokens

    @classmethod
    def tokenize(cls, text: str) -> set[str]:
        return {
            token
            for token in cls.TOKEN_PATTERN.findall(str(text or "").casefold())
            if len(token) > 2 and token not in cls.STOPWORDS
        }
