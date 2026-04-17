"""Detects and consolidates multi-part verbatim answers (e.g. 'Top 3 Words: Word 1/2/3') into a single column."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.services.cleaning_services._patterns import (
    MULTIPART_VERBATIM_SUFFIX_PATTERNS,
    NUMERIC_HEADER_PREFIX_PATTERN,
    TRANSFORMED_COLUMN_INDEX_SUFFIX_PATTERN,
)
from app.services.cleaning_services.text_normalization_service import TextNormalizationService


@dataclass(slots=True)
class MultipartVerbatimPart:
    """Parsed metadata for one part of a multi-part verbatim column (e.g. 'Question: Word 2')."""

    column_name: str
    base_label: str   # Shared stem across all parts (e.g. "Top 3 words")
    group_key: str    # Casefolded base_label used to group parts together
    slot_label: str   # Slot type keyword, e.g. "word", "answer"
    slot_index: int   # Numeric ordinal from the column header (1, 2, 3, ...)
    column_order: int # Original column position, used as a tie-breaker when sorting parts


class MultipartVerbatimConsolidationService:
    """Merges multi-part verbatim answers such as Word 1 / Word 2 / Word 3 into one column."""

    WORD_SEPARATOR = ", "
    DEFAULT_SEPARATOR = " | "

    def __init__(self, text_normalizer: TextNormalizationService) -> None:
        self.text_normalizer = text_normalizer

    def consolidate(
        self,
        df: pd.DataFrame,
        *,
        metadata_columns: list[str],
    ) -> pd.DataFrame:
        if df.empty:
            return df.copy()

        metadata_columns = [column for column in metadata_columns if column in df.columns]
        metadata_set = set(metadata_columns)
        verbatim_columns = [column for column in df.columns if column not in metadata_set]
        if len(verbatim_columns) < 2:
            return df.copy()

        part_by_column: dict[str, MultipartVerbatimPart] = {}
        grouped_parts: dict[str, list[MultipartVerbatimPart]] = {}
        for order, column in enumerate(verbatim_columns):
            part = self._build_part(str(column), order)
            if part is None:
                continue
            part_by_column[column] = part
            grouped_parts.setdefault(part.group_key, []).append(part)

        if not any(len(parts) >= 2 for parts in grouped_parts.values()):
            return df.copy()

        consolidated_columns: dict[str, pd.Series] = {}
        for column in metadata_columns:
            consolidated_columns[column] = df[column]

        used_labels = set(consolidated_columns)
        handled_groups: set[str] = set()
        for column in verbatim_columns:
            part = part_by_column.get(column)
            if part is None or len(grouped_parts[part.group_key]) < 2:
                consolidated_columns[column] = df[column]
                used_labels.add(column)
                continue

            if part.group_key in handled_groups:
                continue

            handled_groups.add(part.group_key)
            group_parts = sorted(
                grouped_parts[part.group_key],
                key=lambda item: (item.slot_index, item.column_order),
            )
            separator = self._separator_for_group(group_parts)
            output_label = self._make_unique_label(part.base_label, used_labels)
            consolidated_columns[output_label] = self._combine_columns(
                df,
                [item.column_name for item in group_parts],
                separator,
            )

        return pd.DataFrame(consolidated_columns, index=df.index)

    def _build_part(self, column_name: str, column_order: int) -> MultipartVerbatimPart | None:
        normalized = self.text_normalizer.normalize_scalar(column_name)
        normalized = str(normalized) if normalized not in (None, "") else column_name.strip()
        normalized = TRANSFORMED_COLUMN_INDEX_SUFFIX_PATTERN.sub("", normalized).strip()
        normalized = NUMERIC_HEADER_PREFIX_PATTERN.sub("", normalized).strip()
        normalized = re.sub(r"\s+", " ", normalized).strip()

        for pattern in MULTIPART_VERBATIM_SUFFIX_PATTERNS:
            match = pattern.match(normalized)
            if not match:
                continue

            base_label = match.group("base").strip()
            slot_label = match.group("slot_label").casefold()
            slot_index = int(match.group("slot_index"))
            if not base_label:
                return None

            return MultipartVerbatimPart(
                column_name=column_name,
                base_label=base_label,
                group_key=base_label.casefold(),
                slot_label=slot_label,
                slot_index=slot_index,
                column_order=column_order,
            )
        return None

    def _separator_for_group(self, group_parts: list[MultipartVerbatimPart]) -> str:
        # "Word N" parts represent single vocabulary items; join with comma for natural reading.
        # All other part types (answer, comment, …) are joined with " | " to preserve boundaries.
        if all(part.slot_label == "word" for part in group_parts):
            return self.WORD_SEPARATOR
        return self.DEFAULT_SEPARATOR

    def _combine_columns(
        self,
        df: pd.DataFrame,
        column_names: list[str],
        separator: str,
    ) -> pd.Series:
        # Build stripped, empty-string-for-null series per column, then merge iteratively.
        # This is fully vectorised and avoids apply(axis=1) and stack() entirely.
        texts = [
            df[col].where(df[col].notna(), "").astype(str).str.strip()
            for col in column_names
        ]
        result = texts[0].copy()
        for text in texts[1:]:
            both = (result != "") & (text != "")
            only_right = (result == "") & (text != "")
            result = result.where(~both, result + separator + text)
            result = result.where(~only_right, text)
        return result.where(result != "", other=None)

    @staticmethod
    def _combine_row_values(values: list[Any], separator: str) -> str | None:
        combined_values: list[str] = []
        for value in values:
            if value is None or pd.isna(value):
                continue
            text = str(value).strip()
            if not text:
                continue
            combined_values.append(text)
        if not combined_values:
            return None
        return separator.join(combined_values)

    @staticmethod
    def _make_unique_label(label: str, used_labels: set[str]) -> str:
        if label not in used_labels:
            used_labels.add(label)
            return label

        suffix = 2
        while True:
            candidate = f"{label} ({suffix})"
            if candidate not in used_labels:
                used_labels.add(candidate)
                return candidate
            suffix += 1
