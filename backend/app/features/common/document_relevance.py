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
            "resource",
            "resources",
            "so",
            "that",
            "the",
            "their",
            "this",
            "to",
            "too",
            "surveysense",
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
        label_tokens = cls.tokenize(str(label or ""))
        label_bigrams = cls.ngrams(cls.tokenize_ordered(str(label or "")), ngram_size=2)
        label_trigrams = cls.ngrams(cls.tokenize_ordered(str(label or "")), ngram_size=3)
        term_tokens = cls.build_relevance_tokens("", terms)
        if not records or not (label_tokens or label_bigrams or label_trigrams or term_tokens):
            return list(records)

        scored_records: list[tuple[tuple[int, int, int, int, int, int, int], TextRecordT]] = []
        for original_index, record in enumerate(records):
            text = str(record.text or "")
            document_tokens = cls.tokenize(text)
            document_token_list = cls.tokenize_ordered(text)
            document_bigrams = cls.ngrams(document_token_list, ngram_size=2)
            document_trigrams = cls.ngrams(document_token_list, ngram_size=3)
            label_trigram_count = len(document_trigrams & label_trigrams)
            label_bigram_count = len(document_bigrams & label_bigrams)
            label_word_count = len(document_tokens & label_tokens)
            term_word_count = len(document_tokens & term_tokens)
            word_count = len(cls.TOKEN_PATTERN.findall(text))
            score = (
                -label_trigram_count,
                -label_bigram_count,
                -label_word_count,
                -term_word_count,
                word_count,
                len(text),
                original_index,
            )
            scored_records.append((score, record))

        scored_records.sort(key=lambda item: item[0])
        return [record for _score, record in scored_records]

    @classmethod
    def overlap_count(cls, text: str, *, label: str, terms: list[str]) -> int:
        relevance_tokens = cls.build_relevance_tokens(label, terms)
        if not relevance_tokens:
            return 0
        return len(cls.tokenize(text) & relevance_tokens)

    @classmethod
    def build_relevance_tokens(cls, label: str, terms: list[str]) -> set[str]:
        tokens: set[str] = set()
        for value in [label, *terms]:
            tokens.update(cls.tokenize(str(value or "")))
        return tokens

    @classmethod
    def build_relevance_ngrams(cls, label: str, terms: list[str], *, ngram_size: int) -> set[str]:
        ngrams: set[str] = set()
        for value in [label, *terms]:
            ngrams.update(cls.ngrams(cls.tokenize_ordered(str(value or "")), ngram_size=ngram_size))
        return ngrams

    @staticmethod
    def ngrams(tokens: list[str], *, ngram_size: int) -> set[str]:
        size = max(1, int(ngram_size))
        return {
            " ".join(tokens[index:index + size])
            for index in range(0, len(tokens) - size + 1)
        }

    @classmethod
    def tokenize(cls, text: str) -> set[str]:
        return set(cls.tokenize_ordered(text))

    @classmethod
    def tokenize_ordered(cls, text: str) -> list[str]:
        return [
            token
            for token in cls.TOKEN_PATTERN.findall(str(text or "").casefold())
            if len(token) > 2 and token not in cls.STOPWORDS
        ]
