"""Domain-specific survey preparation services for Twinkl-format vertical survey exports."""
from __future__ import annotations

from typing import Any

import pandas as pd

from app.core.exceptions import ManifestBuildError
from app.services.cleaning_services import TextNormalizationService


METADATA_COLUMNS = [
    "user_id",
    "country",
    "country_group",
    "country_tier",
    "career_category",
    "career_group",
]

DEFAULT_TARGET_MAIN_TITLES = [
    "What more could Twinkl do to give you confidence?",
    "How can Twinkl better support you to achieve excellence in your role?",
    "What more could Twinkl do to save you time?",
    "What more could Twinkl do to help you realise the value of your subscription?",
    "What more could Twinkl do to give you clear evidence and assurance of your pupils' or children's learning progress?",
    "What more could Twinkl do to help you feel empowered and equipped in your role?",
    "What more could Twinkl do to help you feel recognised in your role?",
    "What more could Twinkl do to help you feel connected to others?",
    "Thanks, we'd love to know more about why you'd recommend Twinkl",
    "Thanks, please tell us more about your score",
    "Please tell us more about how we can improve your experience with Twinkl",
]


class UserIdCastingService:
    """Coerces the user_id column to a nullable integer type for consistent join behaviour."""

    def cast(self, df: pd.DataFrame) -> pd.DataFrame:
        casted = df.copy()
        if "user_id" in casted.columns:
            casted["user_id"] = pd.to_numeric(casted["user_id"], errors="coerce").astype("Int64")
        return casted


class FullTitleFallbackService:
    """Populates full_title_fixed by falling back to main_title when full_title is blank."""

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        prepared = df.copy()
        if "full_title" in prepared.columns and "main_title" in prepared.columns:
            prepared["full_title_fixed"] = (
                prepared["full_title"]
                .where(~_is_blank(prepared["full_title"]), prepared["main_title"])
                .fillna("__MISSING_TITLE__")
            )
        elif "full_title" in prepared.columns:
            prepared["full_title_fixed"] = prepared["full_title"].fillna("__MISSING_TITLE__")
        elif "main_title" in prepared.columns:
            prepared["full_title_fixed"] = prepared["main_title"].fillna("__MISSING_TITLE__")
        return prepared


class MainTitleFallbackService:
    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        prepared = df.copy()
        if "main_title" in prepared.columns:
            prepared["main_title_fixed"] = prepared["main_title"].fillna("__MISSING_MAIN__")
        return prepared


class TitleNormalizationColumnsService:
    def __init__(self, text_normalizer: TextNormalizationService) -> None:
        self.text_normalizer = text_normalizer

    def normalize_title(self, value: Any) -> Any:
        if pd.isna(value):
            return value
        return self.text_normalizer.normalize_scalar(value)

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        prepared = df.copy()
        if "main_title_fixed" in prepared.columns:
            prepared["main_title_norm"] = prepared["main_title_fixed"].map(self.normalize_title)
        if "full_title_fixed" in prepared.columns:
            prepared["full_title_norm"] = prepared["full_title_fixed"].map(self.normalize_title)
        return prepared


class WideSurveyPivotService:
    """Pivots a vertical question/answer DataFrame to one wide row per respondent using a multi-level pivot_table."""

    def build(self, df: pd.DataFrame) -> pd.DataFrame:
        required = {"main_title_norm", "full_title_norm", "answer_value"}
        missing = sorted(required.difference(df.columns))
        if missing:
            raise ManifestBuildError(
                f"Wide build requires columns {missing}. Apply the title preparation services first."
            )

        metadata_cols = [column for column in METADATA_COLUMNS if column in df.columns]
        base = df[
            metadata_cols
            + [
                "main_title_norm",
                "full_title_norm",
                "answer_value",
            ]
        ]

        wide = base.pivot_table(
            index=metadata_cols,
            columns=["main_title_norm", "full_title_norm"],
            values="answer_value",
            aggfunc="last",
        )
        return wide.reset_index()


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

        user_id_column = _resolve_user_id_column_label(wide_df)
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

        user_id_column = _resolve_user_id_column_label(analysis_df)
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


class AnswerCoverageService:
    def summarize(self, df: pd.DataFrame) -> dict[str, int]:
        if "user_id" not in df.columns:
            return {
                "total_rows": int(len(df)),
                "total_users": 0,
                "users_with_any_answer": 0,
                "users_with_no_answers": 0,
                "columns": df.columns.tolist(),
            }

        working = df.copy()
        working["user_id"] = pd.to_numeric(working["user_id"], errors="coerce").astype("Int64")
        if "answer_value" in working.columns:
            users_with_any_answer = (
                working.groupby("user_id")["answer_value"]
                .apply(lambda series: (~_is_blank(series)).any())
                .sum()
            )
        else:
            users_with_any_answer = 0

        total_users = int(working["user_id"].nunique(dropna=True))
        return {
            "total_rows": int(len(working)),
            "total_users": total_users,
            "users_with_any_answer": int(users_with_any_answer),
            "users_with_no_answers": int(total_users - users_with_any_answer),
            "columns": working.columns.tolist(),
        }


class CountryFilterService:
    def apply(self, df: pd.DataFrame, country_filter: str | None) -> pd.DataFrame:
        if not country_filter:
            return df.copy()
        if "country" not in df.columns:
            raise ValueError(
                "country_filter was provided but no 'country' column exists in the input data."
            )
        target = self._normalize_country(country_filter)
        if not target:
            return df.copy()
        mask = df["country"].map(self._normalize_country) == target
        return df.loc[mask].copy()

    @staticmethod
    def _normalize_country(value: Any) -> str:
        if pd.isna(value):
            return ""
        return str(value).strip().casefold()


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
            blank_mask = _is_blank(merged[column])
            merged.loc[blank_mask, column] = merged.loc[blank_mask, meta_column]
            merged = merged.drop(columns=[meta_column])
        return merged

    @staticmethod
    def _has_missing_career_metadata(df: pd.DataFrame) -> bool:
        return any(
            _is_blank(df[column]).any()
            for column in ("career_group", "career_category")
            if column in df.columns
        )


def _resolve_user_id_column_label(df: pd.DataFrame) -> str | tuple[str, str] | None:
    if isinstance(df.columns, pd.MultiIndex):
        for column in df.columns:
            if column[0] == "user_id":
                return column
        return None
    if "user_id" in df.columns:
        return "user_id"
    return None


def _is_blank(series: pd.Series) -> pd.Series:
    return series.isna() | (series.astype(str).str.strip() == "")
