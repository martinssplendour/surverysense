"""Builds filter option lists for low-cardinality metadata columns and applies equality filters to DataFrames."""
from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

TRANSFORMED_COLUMN_INDEX_SUFFIX_PATTERN = re.compile(r"__idx_\d+$", re.IGNORECASE)


@dataclass(slots=True)
class MetadataFilterOption:
    value: str
    count: int


@dataclass(slots=True)
class MetadataFilterDefinition:
    column_name: str
    display_name: str
    options: list[MetadataFilterOption]


class MetadataFilterService:
    """Builds and applies equality filters on low-cardinality metadata columns."""

    NON_FILTERABLE_HEADER_TOKENS = {
        "response id",
        "user id",
    }
    # Upper bound on distinct values to show as filter options (prevents ID-like columns becoming filters).
    MAX_UNIQUE_VALUE_COUNT = 120
    # Above this ratio of unique values to total rows the column is too high-cardinality to filter usefully.
    MAX_UNIQUE_RATIO = 0.45
    MAX_OPTION_COUNT = 120
    # Unique-ratio check only applies once a column has at least this many non-blank rows.
    UNIQUE_RATIO_CARDINALITY_FLOOR = 25

    def build_definitions(
        self,
        df: pd.DataFrame,
        *,
        metadata_columns: list[str],
    ) -> list[MetadataFilterDefinition]:
        """Return filter definitions for metadata columns that have 2–120 distinct non-blank values."""
        definitions: list[MetadataFilterDefinition] = []
        for column in metadata_columns:
            if column not in df.columns:
                continue
            if self._is_non_filterable_header(column):
                continue

            value_counts = self._value_counts(df[column])
            if value_counts.empty:
                continue

            unique_count = int(len(value_counts))
            non_blank_count = int(value_counts.sum())
            unique_ratio = unique_count / max(non_blank_count, 1)
            if unique_count < 2:
                continue
            if unique_count > self.MAX_UNIQUE_VALUE_COUNT:
                continue
            if (
                unique_count >= self.UNIQUE_RATIO_CARDINALITY_FLOOR
                and unique_ratio > self.MAX_UNIQUE_RATIO
            ):
                continue

            definitions.append(
                MetadataFilterDefinition(
                    column_name=column,
                    display_name=self._display_name(column),
                    options=[
                        MetadataFilterOption(value=str(value), count=int(count))
                        for value, count in value_counts.head(self.MAX_OPTION_COUNT).items()
                    ],
                )
            )
        return definitions

    def apply_filters(
        self,
        df: pd.DataFrame,
        *,
        filters: dict[str, list[str]] | None,
        allowed_columns: set[str] | None = None,
    ) -> pd.DataFrame:
        """Apply a dict of column→values equality filters to df; raises ValueError for unknown columns."""
        if not filters:
            return df

        filtered_df = df
        for column, raw_values in filters.items():
            if allowed_columns is not None and column not in allowed_columns:
                raise ValueError(f"Unknown filter column '{column}'.")
            if column not in filtered_df.columns:
                raise ValueError(f"Filter column '{column}' is not present in the dataset.")

            exact_values = {
                resolved
                for resolved in (self.resolve_filter_value(value) for value in raw_values)
                if resolved is not None
            }
            if not exact_values:
                continue

            filtered_series = filtered_df[column].map(self.resolve_filter_value)
            filtered_df = filtered_df.loc[filtered_series.isin(exact_values)]

        return filtered_df

    def _value_counts(self, series: pd.Series) -> pd.Series:
        resolved_values = series.map(self.resolve_filter_value).dropna()
        if resolved_values.empty:
            return pd.Series(dtype="int64")
        counts: dict[str, int] = {}
        for value in resolved_values.tolist():
            counts[value] = counts.get(value, 0) + 1
        return pd.Series(counts, dtype="int64")

    @staticmethod
    def resolve_filter_value(value: object) -> str | None:
        if value is None or pd.isna(value):
            return None
        text = str(value)
        if not text.strip():
            return None
        return text

    @staticmethod
    def _display_name(column_name: str) -> str:
        base_name = TRANSFORMED_COLUMN_INDEX_SUFFIX_PATTERN.sub("", column_name.strip())
        base_name = re.sub(r"[_\W]+", " ", base_name).strip()
        if not base_name:
            return column_name
        return " ".join(token.capitalize() for token in base_name.split())

    def _is_non_filterable_header(self, column_name: str) -> bool:
        normalized = self._normalize_header(column_name)
        return any(token in normalized for token in self.NON_FILTERABLE_HEADER_TOKENS)

    @staticmethod
    def _normalize_header(column_name: str) -> str:
        base_name = TRANSFORMED_COLUMN_INDEX_SUFFIX_PATTERN.sub("", column_name.strip())
        return re.sub(r"[_\W]+", " ", base_name.casefold()).strip()
