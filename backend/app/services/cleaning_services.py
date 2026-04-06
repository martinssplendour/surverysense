from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

import pandas as pd


SMART_APOSTROPHES_PATTERN = re.compile(r"[\u2018\u2019\u0060\u00B4\u2032\u0092]")
NUMERIC_HEADER_PREFIX_PATTERN = re.compile(r"^\s*\d+\s*[:.)-]\s*")


class TextNormalizationService:
    """Shared text normalization for muddy survey exports."""

    def normalize_scalar(self, value: Any) -> Any:
        if value is None or pd.isna(value):
            return None
        text = str(value).replace("\ufeff", "")
        text = SMART_APOSTROPHES_PATTERN.sub("'", text)
        text = text.strip().rstrip("'").strip()
        return text

    def clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        return df.apply(lambda col: col.map(self.normalize_scalar))


class NullScrubbingService:
    def scrub_dataframe(self, df: pd.DataFrame, null_equivalents: list[str]) -> pd.DataFrame:
        normalized_nulls = {self._normalize_token(item) for item in null_equivalents}
        normalized_nulls.update({"", "nan", "<na>"})

        def scrub(value: Any) -> Any:
            if value is None or pd.isna(value):
                return None
            token = self._normalize_token(value)
            if token in normalized_nulls:
                return None
            return value

        return df.apply(lambda col: col.map(scrub))

    @staticmethod
    def _normalize_token(value: Any) -> str:
        return str(value).strip().casefold()


class QuestionHeaderResolutionService:
    def __init__(self, text_normalizer: TextNormalizationService) -> None:
        self.text_normalizer = text_normalizer

    def resolve(self, raw_df: pd.DataFrame, question_header_indices: list[int]) -> pd.Series:
        resolved = pd.Series([None] * len(raw_df), index=raw_df.index, dtype=object)
        for idx in question_header_indices:
            candidate = raw_df.iloc[:, idx].map(self.text_normalizer.normalize_scalar)
            candidate = candidate.map(lambda value: None if value in (None, "") else str(value))
            resolved = resolved.where(resolved.notna(), candidate)
        return resolved


@dataclass(slots=True)
class VerbatimHeaderInfo:
    original_header: str
    normalized_header: str
    subject: str | None
    question_family: str | None
    family_key: str


@dataclass(slots=True)
class VerbatimQuestionCandidate:
    column_name: str
    score: float
    is_selected: bool
    reasons: list[str]
    non_blank_count: int
    unique_ratio: float
    avg_length: float
    long_text_ratio: float
    numeric_ratio: float


class VerbatimHeaderCleaningService:
    def __init__(self, text_normalizer: TextNormalizationService) -> None:
        self.text_normalizer = text_normalizer

    def clean_and_sort(
        self,
        df: pd.DataFrame,
        *,
        metadata_columns: list[str],
    ) -> pd.DataFrame:
        if df.empty:
            return df.copy()

        verbatim_columns = [column for column in df.columns if column not in metadata_columns]
        if not verbatim_columns:
            return df.copy()

        infos = [self._build_header_info(column) for column in verbatim_columns]
        family_counts = Counter(
            info.family_key
            for info in infos
            if info.subject and info.question_family and len(info.question_family) <= 80
        )
        repeated_families = {
            family_key
            for family_key, count in family_counts.items()
            if count >= 2
        }

        rename_map: dict[str, str] = {}
        ordered_infos: list[tuple[tuple[int, str, str, str], VerbatimHeaderInfo]] = []
        used_labels: set[str] = set(metadata_columns)
        for info in infos:
            cleaned_label = info.normalized_header
            sort_group = 1
            sort_primary = info.normalized_header.casefold()
            sort_secondary = ""
            if info.family_key in repeated_families and info.subject and info.question_family:
                cleaned_label = f"{info.question_family} | {info.subject}"
                sort_group = 0
                sort_primary = info.question_family.casefold()
                sort_secondary = info.subject.casefold()

            cleaned_label = self._make_unique_label(cleaned_label, used_labels)
            rename_map[info.original_header] = cleaned_label
            ordered_infos.append(
                ((sort_group, sort_primary, sort_secondary, cleaned_label.casefold()), info)
            )

        ordered_infos.sort(key=lambda item: item[0])
        ordered_verbatim_columns = [rename_map[info.original_header] for _, info in ordered_infos]

        cleaned_df = df.rename(columns=rename_map)
        return cleaned_df[metadata_columns + ordered_verbatim_columns]

    def _build_header_info(self, header: str) -> VerbatimHeaderInfo:
        normalized = self.text_normalizer.normalize_scalar(header)
        normalized = str(normalized) if normalized not in (None, "") else str(header).strip()
        normalized = NUMERIC_HEADER_PREFIX_PATTERN.sub("", normalized).strip()

        subject: str | None = None
        question_family: str | None = None
        if ": " in normalized:
            left, right = normalized.split(": ", 1)
            if left.strip() and right.strip():
                subject = left.strip()
                question_family = right.strip()

        family_key = (question_family or normalized).casefold()
        return VerbatimHeaderInfo(
            original_header=header,
            normalized_header=normalized,
            subject=subject,
            question_family=question_family,
            family_key=family_key,
        )

    @staticmethod
    def _make_unique_label(label: str, used_labels: set[str]) -> str:
        if label not in used_labels:
            used_labels.add(label)
            return label

        counter = 2
        while True:
            candidate = f"{label} ({counter})"
            if candidate not in used_labels:
                used_labels.add(candidate)
                return candidate
            counter += 1


class VerbatimQuestionSelectionService:
    OPEN_ENDED_HEADER_TOKENS = {
        "what more",
        "tell us more",
        "please tell",
        "how can",
        "why",
        "comment",
        "feedback",
        "describe",
        "explain",
        "share",
        "support you",
        "improve your experience",
    }
    CLOSED_ENDED_HEADER_TOKENS = {
        "how important",
        "how well",
        "how likely",
        "hours a week",
        "give permission",
        "permission",
        "are you happy",
        "marketing",
        "awareness",
        "usage",
        "better than",
        "less well",
        "the same as",
    }

    def score_columns(
        self,
        df: pd.DataFrame,
        *,
        metadata_columns: list[str],
        min_score: float = 3.5,
    ) -> list[VerbatimQuestionCandidate]:
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
        normalized_header = column_name.strip().casefold()
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

        unique_ratio = non_blank.nunique(dropna=True) / max(len(non_blank), 1)
        avg_length = float(non_blank.str.len().mean())
        long_text_ratio = float((non_blank.str.len() >= 25).mean())
        numeric_ratio = float(pd.to_numeric(non_blank, errors="coerce").notna().mean())
        top_value_ratio = float(non_blank.value_counts(normalize=True, dropna=True).iloc[0])
        short_value_ratio = float((non_blank.str.len() <= 5).mean())

        score = 0.0
        if any(token in normalized_header for token in self.OPEN_ENDED_HEADER_TOKENS):
            score += 2.5
            reasons.append("header looks open-ended")
        if any(token in normalized_header for token in self.CLOSED_ENDED_HEADER_TOKENS):
            score -= 2.5
            reasons.append("header looks closed-ended or rating-based")
        if "|" in column_name:
            score -= 2.0
            reasons.append("matrix-style header pattern")

        if avg_length >= 40:
            score += 2.0
            reasons.append("answers are long-form")
        elif avg_length >= 20:
            score += 1.0
            reasons.append("answers are moderately long")
        else:
            score -= 1.0
            reasons.append("answers are short")

        if long_text_ratio >= 0.35:
            score += 1.5
            reasons.append("many answers are long text")
        elif long_text_ratio >= 0.15:
            score += 0.5

        if unique_ratio >= 0.65:
            score += 1.5
            reasons.append("answers are highly varied")
        elif unique_ratio >= 0.35:
            score += 0.75

        if numeric_ratio <= 0.1:
            score += 0.5
        else:
            score -= 2.0
            reasons.append("answers are mostly numeric/coded")

        if top_value_ratio <= 0.3:
            score += 0.75
        elif top_value_ratio >= 0.6:
            score -= 1.5
            reasons.append("answers are dominated by one repeated value")

        if short_value_ratio >= 0.7:
            score -= 1.0
            reasons.append("most answers are very short")

        return VerbatimQuestionCandidate(
            column_name=column_name,
            score=score,
            is_selected=score >= min_score,
            reasons=reasons,
            non_blank_count=int(len(non_blank)),
            unique_ratio=unique_ratio,
            avg_length=avg_length,
            long_text_ratio=long_text_ratio,
            numeric_ratio=numeric_ratio,
        )


class VerticalRecordFilterService:
    def drop_invalid_rows(
        self,
        record_df: pd.DataFrame,
        *,
        key_columns: list[str],
        question_column: str,
        answer_column: str,
    ) -> pd.DataFrame:
        if record_df.empty:
            return record_df.copy()

        key_mask = record_df[key_columns].notna().all(axis=1)
        question_mask = record_df[question_column].notna()
        answer_mask = record_df[answer_column].notna()
        return record_df.loc[key_mask & question_mask & answer_mask].copy()


class DuplicateAnswerResolutionService:
    def resolve(
        self,
        record_df: pd.DataFrame,
        *,
        key_columns: list[str],
        question_column: str,
        answer_column: str,
        order_column: str,
    ) -> pd.DataFrame:
        if record_df.empty:
            return record_df.copy()

        deduped = (
            record_df.sort_values(order_column)
            .drop_duplicates(subset=key_columns + [question_column, answer_column], keep="last")
            .drop_duplicates(subset=key_columns + [question_column], keep="last")
        )
        return deduped.reset_index(drop=True)


class MetadataConsolidationService:
    def consolidate(
        self,
        raw_df: pd.DataFrame,
        *,
        key_indices: list[int],
        metadata_indices: list[int],
        column_name_builder: callable,
    ) -> pd.DataFrame:
        selected_indices = list(dict.fromkeys(key_indices + metadata_indices))
        consolidated = pd.DataFrame(
            {
                column_name_builder(raw_df.columns[idx], idx): raw_df.iloc[:, idx]
                for idx in selected_indices
            }
        )
        key_columns = [
            column_name_builder(raw_df.columns[idx], idx)
            for idx in key_indices
        ]
        value_columns = [column for column in consolidated.columns if column not in key_columns]
        if not value_columns:
            return consolidated.drop_duplicates(subset=key_columns).reset_index(drop=True)

        grouped = (
            consolidated.groupby(key_columns, dropna=False, sort=False)[value_columns]
            .agg(self._first_non_null)
            .reset_index()
        )
        return grouped

    @staticmethod
    def _first_non_null(series: pd.Series) -> Any:
        non_null = series.dropna()
        if non_null.empty:
            return None
        return non_null.iloc[0]


class VerticalRecordAssemblyService:
    def assemble(
        self,
        record_df: pd.DataFrame,
        *,
        key_columns: list[str],
        question_column: str,
        answer_column: str,
    ) -> pd.DataFrame:
        if record_df.empty:
            return pd.DataFrame(columns=key_columns)

        wide_df = (
            record_df.pivot(index=key_columns, columns=question_column, values=answer_column)
            .reset_index()
        )
        wide_df.columns.name = None
        return wide_df


class VerbatimRowFilterService:
    def drop_empty_rows(self, df: pd.DataFrame, verbatim_columns: list[str]) -> pd.DataFrame:
        if not verbatim_columns:
            return df.reset_index(drop=True)
        mask = df[verbatim_columns].notna().any(axis=1)
        return df.loc[mask].reset_index(drop=True)
