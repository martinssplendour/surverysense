from __future__ import annotations

import re

from app.features.analysis.topic_analysis_services.contracts import AnalysisExampleRecord
from app.features.analysis.topic_analysis_services.keyword_service import TopicAnalysisKeywordService


class TopicAnalysisNarrativeService:
    REQUEST_CUES = frozenset({"need", "needs", "more", "better", "clearer", "support", "help", "would", "could", "please", "want"})
    POSITIVE_CUES = frozenset({"love", "great", "helpful", "useful", "excellent", "amazing", "valuable", "enjoy", "good"})
    NEGATIVE_CUES = frozenset({"hard", "difficult", "issue", "problem", "frustrating", "missing", "lack", "limited", "confusing"})
    UNCERTAIN_CUES = frozenset({"unsure", "unclear", "unknown", "dont", "don't", "none", "nothing"})

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

        phrase = self._build_phrase(texts=texts, terms=terms, prefer_terms=prefer_terms)
        if not phrase:
            return f"{fallback_prefix} {fallback_id}"

        intent = self._detect_intent(texts)
        if intent == "request":
            return f"Requests for {phrase}"
        if intent == "positive":
            return f"Positive feedback on {phrase}"
        if intent == "negative":
            return f"Challenges with {phrase}"
        if intent == "uncertain":
            return f"Unclear responses about {phrase}"
        return f"Responses about {phrase}"

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
        fallback_terms = [term.replace("_", " ").strip() for term in terms[:2] if term]
        if prefer_terms and fallback_terms:
            return self._normalize_phrase(" ".join(fallback_terms))

        phrase = self.keyword_service.top_phrase(texts).replace("_", " ").strip()
        if phrase:
            return self._normalize_phrase(phrase)

        return self._normalize_phrase(" ".join(fallback_terms))

    def _normalize_phrase(self, phrase: str) -> str:
        normalized = re.sub(r"\s+", " ", phrase).strip(" ,.-")
        return normalized.lower()

    def _detect_intent(self, texts: list[str]) -> str:
        scores = {"request": 0, "positive": 0, "negative": 0, "uncertain": 0}
        for text in texts:
            tokens = set()
            for token in self.keyword_service.TOKEN_PATTERN.findall(text.casefold()):
                normalized = token.strip("-'")
                if len(normalized) < 2:
                    continue
                if normalized.isdigit():
                    continue
                tokens.add(normalized)
            scores["request"] += sum(1 for token in tokens if token in self.REQUEST_CUES)
            scores["positive"] += sum(1 for token in tokens if token in self.POSITIVE_CUES)
            scores["negative"] += sum(1 for token in tokens if token in self.NEGATIVE_CUES)
            scores["uncertain"] += sum(1 for token in tokens if token in self.UNCERTAIN_CUES)

        best_intent = max(scores, key=lambda key: scores[key])
        return best_intent if scores[best_intent] > 0 else "neutral"
