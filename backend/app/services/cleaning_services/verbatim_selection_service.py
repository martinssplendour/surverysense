"""Scores and selects open-text verbatim columns from a transformed DataFrame using heuristic signals."""
from __future__ import annotations

import re
import warnings
from dataclasses import dataclass

import pandas as pd

from app.services.cleaning_services._patterns import TRANSFORMED_COLUMN_INDEX_SUFFIX_PATTERN
from app.services.cleaning_services.metadata_selection_service import MetadataColumnSelectionService


@dataclass(slots=True)
class VerbatimQuestionCandidate:
    """Scored assessment of a single DataFrame column as a candidate open-text verbatim question."""

    column_name: str
    score: float         # Heuristic score; -999 means definitively rejected
    is_selected: bool
    reasons: list[str]   # Human-readable explanation of the selection decision
    non_blank_count: int
    unique_ratio: float  # Fraction of non-blank values that are unique
    avg_length: float    # Mean character length of non-blank answers
    long_text_ratio: float  # Fraction of answers with >= 25 characters
    numeric_ratio: float    # Fraction of values parseable as a number


class VerbatimQuestionSelectionService:
    """Identifies open-text verbatim columns via a cascade of heuristic filters on content and header signals."""

    HIGH_VARIATION_UNIQUE_RATIO_MIN = 0.35
    HIGH_VARIATION_TOP10_COVERAGE_MAX = 0.55
    HIGH_VARIATION_UNIQUE_COUNT_MIN = 10
    MIN_VARIATION_ROW_COUNT = 20
    SHORT_TEXT_AVG_LENGTH_MAX = 20.0
    SHORT_TEXT_LONG_RATIO_MAX = 0.2
    SHORT_TEXT_TOP10_COVERAGE_MAX = 0.75
    SHORT_TEXT_UNIQUE_COUNT_MIN = 8
    SMALL_SAMPLE_FIXED_RESPONSE_MIN_ROWS = 8
    SMALL_SAMPLE_FIXED_RESPONSE_UNIQUE_COUNT_MAX = 5
    SMALL_SAMPLE_FIXED_RESPONSE_UNIQUE_RATIO_MAX = 0.35
    SMALL_SAMPLE_FIXED_RESPONSE_TOP5_COVERAGE_MIN = 0.85
    LOW_VARIATION_UNIQUE_COUNT_MAX = 12
    LOW_VARIATION_UNIQUE_RATIO_MAX = 0.1
    LOW_VARIATION_TOP5_COVERAGE_MIN = 0.65
    LOW_VARIATION_TOP10_COVERAGE_MIN = 0.8
    IDENTIFIER_NUMERIC_RATIO_MIN = 0.95
    IDENTIFIER_UNIQUE_RATIO_MIN = 0.85
    OPEN_ENDED_HEADER_PHRASES = (
        "what more",
        "how can",
        "tell us more",
        "please tell",
        "in your own words",
        "comes to mind",
        "other than",
        "three words",
        "why do",
        "why did",
    )
    OPEN_ENDED_HEADER_TOKENS = {
        "comment",
        "comments",
        "describe",
        "feedback",
        "opinion",
        "share",
        "why",
    }
    CLOSED_QUESTION_HEADER_PHRASES = (
        "how important",
        "how well do we",
        "how likely",
        "how many",
        "which of the following",
        "are you happy",
        "awareness and usage",
        "i have heard of this",
        "i have used this",
    )
    DATETIME_HEADER_TOKENS = {
        "completed",
        "date",
        "submitted",
        "time",
        "timestamp",
    }
    DATETIME_PARSE_RATIO_MIN = 0.9
    NUMERIC_CONTENT_SAMPLE_SIZE = 25
    NUMERIC_CONTENT_RATIO_MAX = 0.5

    def score_columns(
        self,
        df: pd.DataFrame,
        *,
        metadata_columns: list[str],
        min_score: float = 3.5,
    ) -> list[VerbatimQuestionCandidate]:
        """Return one scored candidate per non-metadata column, detailing whether it was selected and why."""
        candidates: list[VerbatimQuestionCandidate] = []
        for column in df.columns:
            if column in metadata_columns:
                continue
            candidate = self._score_column(df[column], column, min_score=min_score)
            candidates.append(candidate)
        return candidates

    def select_columns(
        self,
        df: pd.DataFrame,
        *,
        metadata_columns: list[str],
        min_score: float = 3.5,
    ) -> list[str]:
        return [
            candidate.column_name
            for candidate in self.score_columns(df, metadata_columns=metadata_columns, min_score=min_score)
            if candidate.is_selected
        ]

    def filter_dataframe(
        self,
        df: pd.DataFrame,
        *,
        metadata_columns: list[str],
        min_score: float = 3.5,
    ) -> pd.DataFrame:
        selected_columns = self.select_columns(df, metadata_columns=metadata_columns, min_score=min_score)
        return df[metadata_columns + selected_columns].copy()

    def _score_column(
        self,
        series: pd.Series,
        column_name: str,
        *,
        min_score: float,
    ) -> VerbatimQuestionCandidate:
        non_blank = series.dropna().astype(str).str.strip()
        non_blank = non_blank[non_blank != ""]
        normalized_header = self._normalize_header(column_name)
        reasons: list[str] = []

        if non_blank.empty:
            return VerbatimQuestionCandidate(
                column_name=column_name,
                score=-999.0,
                is_selected=False,
                reasons=["column has no non-blank answers"],
                non_blank_count=0,
                unique_ratio=0.0,
                avg_length=0.0,
                long_text_ratio=0.0,
                numeric_ratio=0.0,
            )

        unique_count = int(non_blank.nunique(dropna=True))
        unique_ratio = unique_count / max(len(non_blank), 1)
        avg_length = float(non_blank.str.len().mean())
        # "long text" threshold of 25 chars distinguishes short label answers from genuine prose.
        long_text_ratio = float((non_blank.str.len() >= 25).mean())
        numeric_ratio = float(pd.to_numeric(non_blank, errors="coerce").notna().mean())
        # Regex matches any Unicode letter — values with no letters at all are not text.
        text_value_ratio = float(non_blank.str.contains(r"[^\W\d_]", regex=True).mean())
        datetime_ratio = self._datetime_value_ratio(non_blank)
        numeric_content_ratio = self._numeric_content_ratio(non_blank)
        value_distribution = non_blank.value_counts(normalize=True, dropna=True)
        top5_coverage = float(value_distribution.head(5).sum())
        top10_coverage = float(value_distribution.head(10).sum())
        header_has_open_cue = self._has_open_ended_header_cue(normalized_header)
        header_looks_closed = self._looks_like_closed_question_header(normalized_header)

        if self._looks_like_identifier_header(normalized_header.split()):
            return VerbatimQuestionCandidate(
                column_name=column_name,
                score=-999.0,
                is_selected=False,
                reasons=["identifier-like header"],
                non_blank_count=int(len(non_blank)),
                unique_ratio=unique_ratio,
                avg_length=avg_length,
                long_text_ratio=long_text_ratio,
                numeric_ratio=numeric_ratio,
            )

        if numeric_ratio >= 1.0:
            return VerbatimQuestionCandidate(
                column_name=column_name,
                score=-999.0,
                is_selected=False,
                reasons=["column is entirely numeric"],
                non_blank_count=int(len(non_blank)),
                unique_ratio=unique_ratio,
                avg_length=avg_length,
                long_text_ratio=long_text_ratio,
                numeric_ratio=numeric_ratio,
            )

        if (
            len(non_blank) >= self.MIN_VARIATION_ROW_COUNT
            and numeric_ratio >= self.IDENTIFIER_NUMERIC_RATIO_MIN
            and unique_ratio >= self.IDENTIFIER_UNIQUE_RATIO_MIN
        ):
            return VerbatimQuestionCandidate(
                column_name=column_name,
                score=-999.0,
                is_selected=False,
                reasons=["column looks like identifier values"],
                non_blank_count=int(len(non_blank)),
                unique_ratio=unique_ratio,
                avg_length=avg_length,
                long_text_ratio=long_text_ratio,
                numeric_ratio=numeric_ratio,
            )

        if text_value_ratio <= 0.0:
            return VerbatimQuestionCandidate(
                column_name=column_name,
                score=-999.0,
                is_selected=False,
                reasons=["column does not contain text responses"],
                non_blank_count=int(len(non_blank)),
                unique_ratio=unique_ratio,
                avg_length=avg_length,
                long_text_ratio=long_text_ratio,
                numeric_ratio=numeric_ratio,
            )

        if numeric_content_ratio >= self.NUMERIC_CONTENT_RATIO_MAX:
            return VerbatimQuestionCandidate(
                column_name=column_name,
                score=-999.0,
                is_selected=False,
                reasons=["column content is mostly numeric"],
                non_blank_count=int(len(non_blank)),
                unique_ratio=unique_ratio,
                avg_length=avg_length,
                long_text_ratio=long_text_ratio,
                numeric_ratio=numeric_ratio,
            )

        if self._looks_like_datetime_header(normalized_header) and datetime_ratio >= self.DATETIME_PARSE_RATIO_MIN:
            return VerbatimQuestionCandidate(
                column_name=column_name,
                score=-999.0,
                is_selected=False,
                reasons=["column contains date/time values"],
                non_blank_count=int(len(non_blank)),
                unique_ratio=unique_ratio,
                avg_length=avg_length,
                long_text_ratio=long_text_ratio,
                numeric_ratio=numeric_ratio,
            )

        if self._looks_like_high_variation_text(
            non_blank_count=int(len(non_blank)),
            unique_count=unique_count,
            unique_ratio=unique_ratio,
            top10_coverage=top10_coverage,
        ):
            if self._looks_like_short_text_label_set(
                avg_length=avg_length,
                long_text_ratio=long_text_ratio,
            ) and not header_has_open_cue:
                return VerbatimQuestionCandidate(
                    column_name=column_name,
                    score=-999.0,
                    is_selected=False,
                    reasons=["short structured answers without open-ended question cues"],
                    non_blank_count=int(len(non_blank)),
                    unique_ratio=unique_ratio,
                    avg_length=avg_length,
                    long_text_ratio=long_text_ratio,
                    numeric_ratio=numeric_ratio,
                )
            reasons.append("column contains text responses")
            reasons.append("answers are highly varied")
            return VerbatimQuestionCandidate(
                column_name=column_name,
                score=10.0,
                is_selected=True,
                reasons=reasons,
                non_blank_count=int(len(non_blank)),
                unique_ratio=unique_ratio,
                avg_length=avg_length,
                long_text_ratio=long_text_ratio,
                numeric_ratio=numeric_ratio,
            )

        if "|" in column_name:
            return VerbatimQuestionCandidate(
                column_name=column_name,
                score=-999.0,
                is_selected=False,
                reasons=["pipe-separated matrix header"],
                non_blank_count=int(len(non_blank)),
                unique_ratio=unique_ratio,
                avg_length=avg_length,
                long_text_ratio=long_text_ratio,
                numeric_ratio=numeric_ratio,
            )

        if self._looks_like_fixed_response_text(
            non_blank_count=int(len(non_blank)),
            unique_count=unique_count,
            unique_ratio=unique_ratio,
            top5_coverage=top5_coverage,
            top10_coverage=top10_coverage,
        ):
            return VerbatimQuestionCandidate(
                column_name=column_name,
                score=-999.0,
                is_selected=False,
                reasons=["answers look like a fixed-response text set"],
                non_blank_count=int(len(non_blank)),
                unique_ratio=unique_ratio,
                avg_length=avg_length,
                long_text_ratio=long_text_ratio,
                numeric_ratio=numeric_ratio,
            )

        if header_looks_closed and self._looks_like_short_text_label_set(
            avg_length=avg_length,
            long_text_ratio=long_text_ratio,
        ):
            return VerbatimQuestionCandidate(
                column_name=column_name,
                score=-999.0,
                is_selected=False,
                reasons=["closed-question header with short structured answers"],
                non_blank_count=int(len(non_blank)),
                unique_ratio=unique_ratio,
                avg_length=avg_length,
                long_text_ratio=long_text_ratio,
                numeric_ratio=numeric_ratio,
            )

        if self._looks_like_short_text_label_set(
            avg_length=avg_length,
            long_text_ratio=long_text_ratio,
        ):
            if not header_has_open_cue:
                return VerbatimQuestionCandidate(
                    column_name=column_name,
                    score=-999.0,
                    is_selected=False,
                    reasons=["short answers need stronger open-ended question cues"],
                    non_blank_count=int(len(non_blank)),
                    unique_ratio=unique_ratio,
                    avg_length=avg_length,
                    long_text_ratio=long_text_ratio,
                    numeric_ratio=numeric_ratio,
                )
            if unique_count < self.SHORT_TEXT_UNIQUE_COUNT_MIN and top10_coverage > self.SHORT_TEXT_TOP10_COVERAGE_MAX:
                return VerbatimQuestionCandidate(
                    column_name=column_name,
                    score=-999.0,
                    is_selected=False,
                    reasons=["short answers do not show enough open-text variation"],
                    non_blank_count=int(len(non_blank)),
                    unique_ratio=unique_ratio,
                    avg_length=avg_length,
                    long_text_ratio=long_text_ratio,
                    numeric_ratio=numeric_ratio,
                )

        reasons.append("column contains text responses")
        reasons.append("answers are sufficiently varied")

        return VerbatimQuestionCandidate(
            column_name=column_name,
            score=10.0,
            is_selected=True,
            reasons=reasons,
            non_blank_count=int(len(non_blank)),
            unique_ratio=unique_ratio,
            avg_length=avg_length,
            long_text_ratio=long_text_ratio,
            numeric_ratio=numeric_ratio,
        )

    def _looks_like_high_variation_text(
        self,
        *,
        non_blank_count: int,
        unique_count: int,
        unique_ratio: float,
        top10_coverage: float,
    ) -> bool:
        if non_blank_count < self.MIN_VARIATION_ROW_COUNT:
            return False

        if unique_count < self.HIGH_VARIATION_UNIQUE_COUNT_MIN:
            return False

        return (
            unique_ratio >= self.HIGH_VARIATION_UNIQUE_RATIO_MIN
            or top10_coverage <= self.HIGH_VARIATION_TOP10_COVERAGE_MAX
        )

    def _looks_like_fixed_response_text(
        self,
        *,
        non_blank_count: int,
        unique_count: int,
        unique_ratio: float,
        top5_coverage: float,
        top10_coverage: float,
    ) -> bool:
        if (
            non_blank_count >= self.SMALL_SAMPLE_FIXED_RESPONSE_MIN_ROWS
            and top5_coverage >= self.SMALL_SAMPLE_FIXED_RESPONSE_TOP5_COVERAGE_MIN
            and (
                unique_count <= self.SMALL_SAMPLE_FIXED_RESPONSE_UNIQUE_COUNT_MAX
                or unique_ratio <= self.SMALL_SAMPLE_FIXED_RESPONSE_UNIQUE_RATIO_MAX
            )
        ):
            return True

        if non_blank_count < self.MIN_VARIATION_ROW_COUNT:
            return False

        return (
            (unique_count <= self.LOW_VARIATION_UNIQUE_COUNT_MAX and top5_coverage >= self.LOW_VARIATION_TOP5_COVERAGE_MIN)
            or
            (unique_ratio <= self.LOW_VARIATION_UNIQUE_RATIO_MAX and top10_coverage >= self.LOW_VARIATION_TOP10_COVERAGE_MIN)
        )

    def _has_open_ended_header_cue(self, normalized_header: str) -> bool:
        if any(phrase in normalized_header for phrase in self.OPEN_ENDED_HEADER_PHRASES):
            return True
        tokens = set(normalized_header.split())
        return bool(tokens & self.OPEN_ENDED_HEADER_TOKENS)

    def _looks_like_closed_question_header(self, normalized_header: str) -> bool:
        return any(phrase in normalized_header for phrase in self.CLOSED_QUESTION_HEADER_PHRASES)

    def _looks_like_datetime_header(self, normalized_header: str) -> bool:
        tokens = set(normalized_header.split())
        return bool(tokens & self.DATETIME_HEADER_TOKENS)

    @staticmethod
    def _datetime_value_ratio(non_blank: pd.Series) -> float:
        sample = non_blank.head(500)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            parsed = pd.to_datetime(sample, errors="coerce")
        return float(parsed.notna().mean()) if len(sample) else 0.0

    def _numeric_content_ratio(self, non_blank: pd.Series) -> float:
        sample = non_blank.head(self.NUMERIC_CONTENT_SAMPLE_SIZE).astype(str)
        digit_count = int(sample.str.count(r"\d").sum())
        letter_count = int(sample.str.count(r"[^\W\d_]").sum())
        denominator = digit_count + letter_count
        return digit_count / denominator if denominator else 0.0

    def _looks_like_short_text_label_set(
        self,
        *,
        avg_length: float,
        long_text_ratio: float,
    ) -> bool:
        return (
            avg_length <= self.SHORT_TEXT_AVG_LENGTH_MAX
            and long_text_ratio <= self.SHORT_TEXT_LONG_RATIO_MAX
        )

    @staticmethod
    def _normalize_header(column_name: str) -> str:
        base_name = TRANSFORMED_COLUMN_INDEX_SUFFIX_PATTERN.sub("", column_name.strip())
        return re.sub(r"[_\W]+", " ", base_name.casefold()).strip()

    @staticmethod
    def _looks_like_identifier_header(tokens: list[str]) -> bool:
        return MetadataColumnSelectionService._looks_like_identifier_header(tokens)
