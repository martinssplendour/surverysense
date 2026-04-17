"""Record-level cleaning services: validates vertical records, deduplicates answers, consolidates metadata, and assembles wide output."""
from __future__ import annotations

from typing import Any

import pandas as pd


class VerticalRecordFilterService:
    """Drops rows from a vertical record DataFrame that are missing a key, question, or answer value."""

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
    """Resolves duplicate question/answer rows for the same respondent by keeping the last non-null occurrence."""

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

        # Two-pass dedup: first remove exact (key, question, answer) duplicates,
        # then keep the last answer per (key, question) if multiple different answers exist.
        deduped = (
            record_df.sort_values(order_column)
            .drop_duplicates(subset=key_columns + [question_column, answer_column], keep="last")
            .drop_duplicates(subset=key_columns + [question_column], keep="last")
        )
        return deduped.reset_index(drop=True)


class MetadataConsolidationService:
    """Collapses a raw DataFrame to one row per unique key, taking the first non-null value for each metadata column."""

    def consolidate(
        self,
        raw_df: pd.DataFrame,
        *,
        key_indices: list[int],
        metadata_indices: list[int],
        column_name_builder: Any,
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
            .first()
            .reset_index()
        )
        return grouped


class VerticalRecordAssemblyService:
    """Pivots a cleaned vertical record DataFrame into one wide row per respondent with each question as a column."""

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
