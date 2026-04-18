"""Header resolution and cleaning services: resolves question headers in vertical layouts and cleans/sorts verbatim column names."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.services.cleaning_services._patterns import (
    NUMERIC_HEADER_PREFIX_PATTERN,
    TRANSFORMED_COLUMN_INDEX_SUFFIX_PATTERN,
)
from app.services.cleaning_services.text_normalization_service import TextNormalizationService


@dataclass(slots=True)
class VerbatimHeaderInfo:
    """Parsed metadata for one verbatim column header, including its question-family and sub-question subject."""

    original_header: str
    normalized_header: str
    subject: str | None        # The part before ": " (e.g. "Product features" in "Product features: Please explain")
    question_family: str | None  # The part after ": "
    family_key: str            # Casefolded family used for grouping repeated sub-questions


class QuestionHeaderResolutionService:
    """Builds a single question-header Series from multiple fallback columns in a vertical layout."""

    def __init__(self, text_normalizer: TextNormalizationService) -> None:
        self.text_normalizer = text_normalizer

    def resolve(self, raw_df: pd.DataFrame, question_header_indices: list[int]) -> pd.Series:
        """Merge columns at question_header_indices left-to-right, filling nulls from successive fallbacks."""
        resolved = pd.Series([None] * len(raw_df), index=raw_df.index, dtype=object)
        _null_like = frozenset({"nan", "<na>", "none"})
        for idx in question_header_indices:
            # Vectorised: clean the column then filter out empty / null-like strings.
            candidate = self.text_normalizer.clean_series(raw_df.iloc[:, idx])
            bad = candidate.isna() | (candidate == "") | candidate.str.casefold().isin(_null_like)
            candidate = candidate.where(~bad, other=None)
            resolved = resolved.where(resolved.notna(), candidate)
        return resolved

    @staticmethod
    def _normalize_resolved_value(value: Any) -> str | None:
        if value is None or pd.isna(value):
            return None
        text = str(value).strip()
        if not text:
            return None
        if text.casefold() in {"nan", "<na>", "none"}:
            return None
        return text


class VerbatimHeaderCleaningService:
    """Renames and re-orders verbatim columns, grouping repeated sub-questions as 'Family | Subject'."""

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
        # A family is "repeated" only when at least 2 columns share the same question_family text —
        # that's when grouping as "Family | Subject" becomes meaningful.
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
        normalized = TRANSFORMED_COLUMN_INDEX_SUFFIX_PATTERN.sub("", normalized).strip()
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
