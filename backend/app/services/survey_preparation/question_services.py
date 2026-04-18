from __future__ import annotations

import pandas as pd

from app.services.survey_preparation._shared import (
    DEFAULT_TARGET_MAIN_TITLES,
    METADATA_COLUMNS,
    resolve_user_id_column_label,
)
from app.services.survey_preparation.title_preparation import TitleNormalizationColumnsService


class QuestionRecordExtractionService:
    """Extracts per-respondent text records for one question title from a pivoted wide DataFrame."""

    def __init__(self, title_normalizer: TitleNormalizationColumnsService) -> None:
        self.title_normalizer = title_normalizer

    def extract(self, wide_df: pd.DataFrame, question_title: str) -> pd.DataFrame:
        """Return a flat records DataFrame (metadata + full_title + text) for the given question_title."""
        if wide_df.empty:
            return self._empty_question_records()

        normalized_question_title = self.title_normalizer.normalize_title(question_title)
        first_level = set(wide_df.columns.get_level_values(0))
        index_cols = [column for column in METADATA_COLUMNS if column in first_level]
        if "user_id" not in index_cols:
            return self._empty_question_records(index_cols=index_cols)

        wide_idx = wide_df.set_index(index_cols)
        main_levels = wide_idx.columns.get_level_values(0)
        normalized_main_levels = [self.title_normalizer.normalize_title(value) for value in main_levels]
        if normalized_question_title not in set(normalized_main_levels):
            return self._empty_question_records(index_cols=index_cols)

        matching_mask = [
            self.title_normalizer.normalize_title(value) == normalized_question_title
            for value in main_levels
        ]
        question_block = wide_idx.loc[:, matching_mask].copy()
        question_block.columns = question_block.columns.get_level_values(1)
        stacked = question_block.stack(future_stack=True)
        stacked = stacked[stacked.notna()]
        text_series = stacked.astype(str).str.strip()
        text_series = text_series[text_series != ""]
        text_series = text_series[text_series.str.lower() != "nan"]
        text_series = text_series[text_series.str.lower() != "<na>"]
        text_series = text_series[text_series.str.lower() != "none"]

        records = text_series.reset_index()
        records.columns = index_cols + ["full_title", "text"]
        return records

    def _empty_question_records(self, index_cols: list[str] | None = None) -> pd.DataFrame:
        columns = (index_cols or METADATA_COLUMNS.copy()) + ["full_title", "text"]
        return pd.DataFrame(columns=columns)


class QuestionSelectionService:
    def __init__(self, title_normalizer: TitleNormalizationColumnsService) -> None:
        self.title_normalizer = title_normalizer

    def filter_analysis_questions(
        self,
        wide_df: pd.DataFrame,
        target_main_titles: list[str] | None = None,
    ) -> pd.DataFrame:
        if wide_df.empty:
            return wide_df.copy()

        targets = target_main_titles or DEFAULT_TARGET_MAIN_TITLES
        normalized_targets = {self.title_normalizer.normalize_title(value) for value in targets}

        user_id_column = resolve_user_id_column_label(wide_df)
        if user_id_column is not None:
            wide_idx = wide_df.set_index(user_id_column)
            reset_index = True
        else:
            wide_idx = wide_df.copy()
            reset_index = False

        normalized_main_levels = [
            self.title_normalizer.normalize_title(value)
            for value in wide_idx.columns.get_level_values(0)
        ]
        mask = [value in normalized_targets for value in normalized_main_levels]
        analysis_df = wide_idx.loc[:, mask]
        if reset_index:
            analysis_df = analysis_df.reset_index()
        return analysis_df


class QuestionTextService:
    def __init__(self, title_normalizer: TitleNormalizationColumnsService) -> None:
        self.title_normalizer = title_normalizer

    def run(self, analysis_df: pd.DataFrame, main_q: str) -> pd.DataFrame:
        if analysis_df.empty:
            return pd.DataFrame(columns=["user_id", "full_title", "text"])

        user_id_column = resolve_user_id_column_label(analysis_df)
        if user_id_column is None:
            return pd.DataFrame(columns=["user_id", "full_title", "text"])

        wide_idx = analysis_df.set_index(user_id_column)
        normalized_main_q = self.title_normalizer.normalize_title(main_q)
        normalized_levels = [
            self.title_normalizer.normalize_title(value)
            for value in wide_idx.columns.get_level_values(0)
        ]
        if normalized_main_q not in set(normalized_levels):
            return pd.DataFrame(columns=["user_id", "full_title", "text"])

        matching_mask = [value == normalized_main_q for value in normalized_levels]
        question_block = wide_idx.loc[:, matching_mask].copy()
        question_block.columns = question_block.columns.get_level_values(1)
        series = question_block.stack(future_stack=True)
        texts = (
            series.astype(str)
            .str.strip()
            .replace({"nan": ""})
        )
        texts = texts[texts != ""]

        data = texts.reset_index()
        data.columns = ["user_id", "full_title", "text"]
        return data
