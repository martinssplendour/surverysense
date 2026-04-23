from __future__ import annotations

import pandas as pd

from app.features.ingestion.survey_preparation._shared import is_blank
from app.features.ingestion.survey_preparation.question_services import QuestionRecordExtractionService


class CareerMetadataBackfillService:
    """Fills missing career_group / career_category from a separate question record source when the primary records lack them."""

    def __init__(self, question_record_extractor: QuestionRecordExtractionService) -> None:
        self.question_record_extractor = question_record_extractor

    def backfill(
        self,
        rec_df: pd.DataFrame,
        *,
        question_title: str,
        wide_df: pd.DataFrame,
    ) -> pd.DataFrame:
        rec = rec_df.copy()
        for column in ("career_group", "career_category"):
            if column not in rec.columns:
                rec[column] = pd.NA

        if not self._has_missing_career_metadata(rec):
            return rec

        meta = self.question_record_extractor.extract(wide_df, question_title)
        if meta.empty:
            return rec

        needed_cols = [
            column for column in ["user_id", "full_title", "text", "career_group", "career_category"]
            if column in meta.columns
        ]
        meta = meta[needed_cols].drop_duplicates(
            subset=[column for column in ["user_id", "full_title", "text"] if column in needed_cols]
        )
        if meta.empty:
            return rec

        join_keys = [
            column for column in ["user_id", "full_title", "text"]
            if column in rec.columns and column in meta.columns
        ]
        if not join_keys:
            return rec

        merged = rec.merge(meta, on=join_keys, how="left", suffixes=("", "_meta"))
        for column in ("career_group", "career_category"):
            meta_column = f"{column}_meta"
            if meta_column not in merged.columns:
                continue
            blank_mask = is_blank(merged[column])
            merged.loc[blank_mask, column] = merged.loc[blank_mask, meta_column]
            merged = merged.drop(columns=[meta_column])
        return merged

    @staticmethod
    def _has_missing_career_metadata(df: pd.DataFrame) -> bool:
        return any(
            is_blank(df[column]).any()
            for column in ("career_group", "career_category")
            if column in df.columns
        )
