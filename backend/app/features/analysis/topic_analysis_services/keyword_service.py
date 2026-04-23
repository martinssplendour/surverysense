from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable

from app.features.analysis.topic_analysis_services.config import PreparedDocument
from app.features.analysis.topic_analysis_services.contracts import (
    AnalysisDocumentRecord,
    AnalysisNgramItemRecord,
)


class TopicAnalysisKeywordService:
    STOPWORDS = frozenset(
        {
            "a", "about", "after", "again", "all", "also", "an", "and", "any", "are",
            "as", "at", "am", "be", "been", "being", "both", "but", "by", "can",
            "could", "do", "does", "each", "few", "for", "from", "had", "has", "have",
            "he", "her", "here", "hers", "herself", "him", "himself", "his", "how",
            "i", "if", "in", "into", "is", "it", "its", "me", "more", "most", "my",
            "need", "needs", "not", "of", "on", "only", "or", "other", "our", "ours",
            "ourselves", "out", "own", "please", "really", "same", "she", "should",
            "so", "that", "the", "their", "them", "then", "there", "these", "they",
            "this", "those", "to", "too", "us", "very", "was", "we", "were", "what",
            "when", "which", "who", "whom", "why", "will", "with", "would", "you", "your",
        }
    )
    TOKEN_PATTERN = re.compile(r"[^\W_][^\W_'\-]*", re.UNICODE)

    def top_terms(self, texts: list[str], *, top_n: int) -> list[str]:
        counts: Counter[str] = Counter()
        for text in texts:
            counts.update(self._tokenize(text))
        return [term for term, count in counts.most_common() if count > 0][:top_n]

    def top_ngrams(self, texts: list[str], *, ngram_size: int, top_n: int) -> list[dict[str, int | str]]:
        counts: Counter[str] = Counter()
        for text in texts:
            tokens = self._tokenize(text)
            if len(tokens) < ngram_size:
                continue
            counts.update(
                " ".join(tokens[index: index + ngram_size])
                for index in range(len(tokens) - ngram_size + 1)
            )

        return [
            {"term": term, "count": int(count)}
            for term, count in counts.most_common(top_n)
            if count > 0
        ]

    def top_ngrams_with_documents(
        self,
        documents: list[PreparedDocument],
        *,
        ngram_size: int,
        top_n: int,
    ) -> list[AnalysisNgramItemRecord]:
        counts: Counter[str] = Counter()
        matched_documents: dict[str, list[AnalysisDocumentRecord]] = defaultdict(list)
        for document in documents:
            tokens = self._tokenize(document.text)
            if len(tokens) < ngram_size:
                continue

            document_ngrams = [
                " ".join(tokens[index: index + ngram_size])
                for index in range(len(tokens) - ngram_size + 1)
            ]
            counts.update(document_ngrams)

            seen_terms: set[str] = set()
            for term in document_ngrams:
                if term in seen_terms or int(document.row_number) <= 0 or not document.text:
                    continue
                matched_documents[term].append(
                    AnalysisDocumentRecord(
                        row_number=int(document.row_number),
                        text=document.text,
                    )
                )
                seen_terms.add(term)

        return [
            AnalysisNgramItemRecord(
                term=term,
                count=int(count),
                document_count=len(matched_documents.get(term, [])),
                documents=list(matched_documents.get(term, [])),
            )
            for term, count in counts.most_common(top_n)
            if count > 0
        ]

    def build_label(self, terms: list[str], *, fallback_prefix: str, fallback_id: str) -> str:
        if terms:
            return " / ".join(term.replace("_", " ") for term in terms[:3])
        return f"{fallback_prefix} {fallback_id}"

    def sanitize_terms(self, terms: Iterable[str], *, top_n: int | None = None) -> list[str]:
        cleaned_terms: list[str] = []
        seen_terms: set[str] = set()
        for term in terms:
            normalized = self._normalize_term(term)
            if not normalized:
                continue
            key = normalized.casefold()
            if key in seen_terms:
                continue
            seen_terms.add(key)
            cleaned_terms.append(normalized)
            if top_n is not None and len(cleaned_terms) >= top_n:
                break
        return cleaned_terms

    def top_phrase(self, texts: list[str]) -> str:
        trigrams = self.top_ngrams(texts, ngram_size=3, top_n=3)
        for item in trigrams:
            if int(item["count"]) >= 2:
                return str(item["term"])

        bigrams = self.top_ngrams(texts, ngram_size=2, top_n=3)
        for item in bigrams:
            if int(item["count"]) >= 2:
                return str(item["term"])

        terms = self.top_terms(texts, top_n=2)
        return " ".join(terms).strip()

    def _tokenize(self, text: str) -> list[str]:
        tokens: list[str] = []
        for token in self.TOKEN_PATTERN.findall(text.casefold()):
            normalized = token.strip("-'")
            if len(normalized) <= 2:
                continue
            if normalized.isdigit():
                continue
            if normalized in self.STOPWORDS:
                continue
            tokens.append(normalized)
        return tokens

    def _normalize_term(self, term: object) -> str:
        ordered_tokens: list[str] = []
        seen_tokens: set[str] = set()
        for token in self._tokenize(str(term).replace("_", " ")):
            if token in seen_tokens:
                continue
            seen_tokens.add(token)
            ordered_tokens.append(token)
        return " ".join(ordered_tokens)
