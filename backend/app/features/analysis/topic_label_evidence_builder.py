from __future__ import annotations

import re
from collections import Counter

from app.features.analysis.topic_analysis_services.contracts import (
    AnalysisDocumentRecord,
    AnalysisGroupRecord,
    TopicLabelEvidenceGroup,
    TopicLabelNgramEvidence,
)
from app.features.analysis.topic_analysis_services.keyword_service import TopicAnalysisKeywordService


class TopicLabelEvidenceBuilder:
    TOKEN_PATTERN = re.compile(r"[^\W_][^\W_'\-]*", re.UNICODE)
    MAX_CONTEXT_DOCUMENTS = 120
    PHRASE_DOCUMENT_LIMIT = 3
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

    def __init__(
        self,
        *,
        max_groups: int,
        max_examples_per_group: int,
        max_terms_per_group: int,
        max_chars_per_example: int,
        max_unigrams: int = 5,
        max_bigrams: int = 3,
        max_trigrams: int = 3,
        min_ngram_document_count: int = 4,
        keyword_service: TopicAnalysisKeywordService | None = None,
    ) -> None:
        self.max_groups = max_groups
        self.max_tightest_responses = max(1, int(max_examples_per_group))
        self.max_terms_per_group = max_terms_per_group
        self.max_context_phrases_per_group = max(1, max_terms_per_group)
        self.max_chars_per_example = max_chars_per_example
        self.max_unigrams = max(0, int(max_unigrams))
        self.max_bigrams = max(0, int(max_bigrams))
        self.max_trigrams = max(0, int(max_trigrams))
        self.min_ngram_document_count = max(1, int(min_ngram_document_count))
        self.keyword_service = keyword_service or TopicAnalysisKeywordService()

    def build_group_evidence(self, groups: list[AnalysisGroupRecord]) -> list[TopicLabelEvidenceGroup]:
        evidence_groups: list[TopicLabelEvidenceGroup] = []
        group_limit = int(self.max_groups or 0)
        for group in groups:
            if group_limit > 0 and len(evidence_groups) >= group_limit:
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
                    top_unigrams=self.collect_top_ngrams(group, ngram_size=1, top_n=self.max_unigrams),
                    top_bigrams=self.collect_top_ngrams(group, ngram_size=2, top_n=self.max_bigrams),
                    top_trigrams=self.collect_top_ngrams(group, ngram_size=3, top_n=self.max_trigrams),
                    tightest_responses=self.collect_tightest_responses(group),
                )
            )
        return evidence_groups

    def collect_examples(self, group: AnalysisGroupRecord) -> list[str]:
        return self.collect_tightest_responses(group)

    def collect_tightest_responses(self, group: AnalysisGroupRecord) -> list[str]:
        # Group documents are ordered before AI labeling. Use that order directly so
        # the naming evidence is the same response order users see in the modal.
        responses: list[str] = []
        for document in self._collect_group_documents(group):
            text = self._truncate_document_text(self._document_text(document))
            if not text:
                continue
            responses.append(text)
            if len(responses) >= self.max_tightest_responses:
                break
        return responses

    def collect_terms(self, group: AnalysisGroupRecord) -> list[str]:
        max_terms = max(1, self.max_terms_per_group)
        return self.keyword_service.sanitize_terms(group.terms, top_n=max_terms)

    def collect_top_ngrams(
        self,
        group: AnalysisGroupRecord,
        *,
        ngram_size: int,
        top_n: int,
    ) -> list[TopicLabelNgramEvidence]:
        ngram_size = max(1, int(ngram_size))
        top_n = max(0, int(top_n))
        if top_n <= 0:
            return []

        documents = self._collect_group_documents(group)
        if not documents:
            return []

        min_document_count = min(self.min_ngram_document_count, max(1, len(documents)))
        counts: Counter[str] = Counter()
        document_counts: Counter[str] = Counter()
        documents_by_term: dict[str, list[str]] = {}
        for document in documents:
            text = self._document_text(document)
            tokens = self.keyword_service.tokenize_terms(text)
            if len(tokens) < ngram_size:
                continue

            document_terms: set[str] = set()
            for index in range(len(tokens) - ngram_size + 1):
                term = " ".join(tokens[index: index + ngram_size])
                normalized = self._normalize_ngram(term, ngram_size=ngram_size)
                if not normalized:
                    continue
                counts[normalized] += 1
                document_terms.add(normalized)

            for term in document_terms:
                document_counts[term] += 1
                term_documents = documents_by_term.setdefault(term, [])
                if len(term_documents) < self.PHRASE_DOCUMENT_LIMIT:
                    truncated = self._truncate_document_text(text)
                    if truncated:
                        term_documents.append(truncated)

        ranked_terms = sorted(
            (
                (term, int(counts[term]), int(document_counts[term]))
                for term in counts
                if int(document_counts[term]) >= min_document_count
            ),
            key=lambda item: (-item[2], -item[1], item[0]),
        )
        return [
            TopicLabelNgramEvidence(
                term=term,
                count=count,
                document_count=document_count,
                documents=list(documents_by_term.get(term, [])),
            )
            for term, count, document_count in ranked_terms[:top_n]
        ]

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

    def _collect_group_document_texts(self, group: AnalysisGroupRecord) -> list[str]:
        return [
            text
            for document in self._collect_group_documents(group)
            for text in [self._document_text(document)]
            if text
        ]

    def _collect_group_documents(self, group: AnalysisGroupRecord) -> list[AnalysisDocumentRecord]:
        documents = list(group.documents) or list(group.examples)
        return documents[: self.MAX_CONTEXT_DOCUMENTS]

    def _document_text(self, document: AnalysisDocumentRecord) -> str:
        return re.sub(r"\s+", " ", str(document.text or "").strip())

    def _truncate_document_text(self, text: str) -> str:
        max_chars = max(80, self.max_chars_per_example)
        return re.sub(r"\s+", " ", str(text or "").strip())[:max_chars].rstrip()

    def _normalize_ngram(self, term: str, *, ngram_size: int) -> str:
        cleaned_terms = self.keyword_service.sanitize_terms([term], top_n=1)
        if not cleaned_terms:
            return ""
        normalized = cleaned_terms[0]
        if len(normalized.split()) != ngram_size:
            return ""
        return normalized

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
