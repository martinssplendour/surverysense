from __future__ import annotations

import re

from app.features.analysis.topic_analysis_services.contracts import AnalysisExampleRecord
from app.features.analysis.topic_analysis_services.keyword_service import TopicAnalysisKeywordService


class TopicAnalysisNarrativeService:
    LABEL_ACRONYMS = frozenset({"ai", "api", "csv", "pdf", "ppt", "pptx", "uk", "us", "usa"})
    FILLER_PREFIX_TOKENS = frozenset({"existing", "proposed"})
    UNCLEAR_LABEL_PATTERNS = frozenset(
        {
            "don know",
            "dont know",
            "don't know",
            "do not know",
            "not sure",
        }
    )

    def __init__(self, keyword_service: TopicAnalysisKeywordService) -> None:
        self.keyword_service = keyword_service

    def build_label(
        self,
        *,
        texts: list[str],
        terms: list[str],
        is_noise: bool,
        fallback_prefix: str,
        fallback_id: str,
        prefer_terms: bool = False,
    ) -> str:
        if is_noise:
            return "Unassigned responses"

        raw_text_label = self._label_from_raw_texts(texts)
        if raw_text_label:
            return raw_text_label

        phrase = self._build_phrase(texts=texts, terms=terms, prefer_terms=prefer_terms)
        if not phrase:
            return f"{fallback_prefix} {fallback_id}"

        return self._polish_topic_label(self._format_topic_label(phrase), fallback_prefix=fallback_prefix, fallback_id=fallback_id)

    def build_comment(
        self,
        *,
        label: str,
        count: int,
        total_documents: int,
        examples: list[AnalysisExampleRecord],
    ) -> str:
        share = 0 if total_documents <= 0 else round((count / total_documents) * 100)
        row_numbers = [
            int(example.row_number)
            for example in examples
            if isinstance(example.row_number, int)
        ]
        if not row_numbers:
            return f"{label} appears in {count} response(s), representing {share}% of the filtered sample."

        if len(row_numbers) == 1:
            reference_text = f"Representative document: row {row_numbers[0]}."
        else:
            joined = ", ".join(str(value) for value in row_numbers)
            reference_text = f"Representative documents: rows {joined}."

        return f"{label} appears in {count} response(s), representing {share}% of the filtered sample. {reference_text}"

    def _build_phrase(self, *, texts: list[str], terms: list[str], prefer_terms: bool = False) -> str:
        fallback_terms = self.keyword_service.sanitize_terms(terms, top_n=2)
        if prefer_terms and fallback_terms:
            return self._normalize_phrase(" ".join(fallback_terms))

        phrase = self.keyword_service.top_phrase(texts).replace("_", " ").strip()
        if phrase:
            return self._normalize_phrase(phrase)

        return self._normalize_phrase(" ".join(fallback_terms))

    def _normalize_phrase(self, phrase: str) -> str:
        normalized = re.sub(r"\s+", " ", phrase).strip(" ,.-")
        return normalized.lower()

    def _format_topic_label(self, phrase: str) -> str:
        normalized = self._normalize_phrase(phrase)
        if not normalized:
            return ""
        return " ".join(self._format_label_token(token) for token in normalized.split())

    def _format_label_token(self, token: str) -> str:
        parts = token.split("-")
        return "-".join(self._format_label_token_part(part) for part in parts)

    def _format_label_token_part(self, token: str) -> str:
        if token in self.LABEL_ACRONYMS:
            return token.upper()
        return token[:1].upper() + token[1:]

    def _polish_topic_label(self, label: str, *, fallback_prefix: str, fallback_id: str) -> str:
        tokens = self._normalize_phrase(label).split()
        if not tokens:
            return f"{fallback_prefix} {fallback_id}"

        normalized = " ".join(tokens)
        unique_tokens = set(tokens)
        if normalized in self.UNCLEAR_LABEL_PATTERNS or ({"don", "know"}.issubset(unique_tokens)):
            return "Unclear Or Unsure Feedback"
        if len(tokens) >= 2 and len(unique_tokens) == 1:
            return "Unclear Or Repeated Feedback"
        if {"printed", "bound", "teacher"}.issubset(unique_tokens):
            return "Printed Teaching Materials"
        if normalized == "proposed activities":
            return "Activity Suggestions"
        if normalized == "confidence twinkl":
            return "Confidence In Twinkl"
        if len(tokens) > 2 and tokens[0] in self.FILLER_PREFIX_TOKENS:
            tokens = tokens[1:]

        polished = " ".join(self._format_label_token(token) for token in tokens)
        if len(tokens) < 2:
            return f"{fallback_prefix} {fallback_id}"
        return polished

    def _label_from_raw_texts(self, texts: list[str]) -> str:
        normalized_texts = [
            self._normalize_phrase(text)
            for text in texts
            if str(text or "").strip()
        ]
        if not normalized_texts:
            return ""

        if any(text in self.UNCLEAR_LABEL_PATTERNS or "don't know" in text for text in normalized_texts):
            return "Unclear Or Unsure Feedback"

        compact_texts = [text for text in normalized_texts if text]
        unique_texts = set(compact_texts)
        if len(unique_texts) == 1:
            repeated_tokens = compact_texts[0].split()
            if len(repeated_tokens) >= 2 and len(set(repeated_tokens)) == 1:
                return "Unclear Or Repeated Feedback"

        return ""
