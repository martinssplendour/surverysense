from __future__ import annotations

from typing import Any

import pandas as pd

METADATA_COLUMNS = [
    "user_id",
    "country",
    "country_group",
    "country_tier",
    "career_category",
    "career_group",
]

DEFAULT_TARGET_MAIN_TITLES = [
    "What more could SurveySense do to give you confidence?",
    "How can SurveySense better support you to achieve excellence in your role?",
    "What more could SurveySense do to save you time?",
    "What more could SurveySense do to help you realise the value of your subscription?",
    "What more could SurveySense do to give you clear evidence and assurance of your pupils' or children's learning progress?",
    "What more could SurveySense do to help you feel empowered and equipped in your role?",
    "What more could SurveySense do to help you feel recognised in your role?",
    "What more could SurveySense do to help you feel connected to others?",
    "Thanks, we'd love to know more about why you'd recommend SurveySense",
    "Thanks, please tell us more about your score",
    "Please tell us more about how we can improve your experience with SurveySense",
]


def resolve_user_id_column_label(df: pd.DataFrame) -> str | tuple[str, str] | None:
    if isinstance(df.columns, pd.MultiIndex):
        for column in df.columns:
            if column[0] == "user_id":
                return column
        return None
    if "user_id" in df.columns:
        return "user_id"
    return None


def is_blank(series: pd.Series) -> pd.Series:
    return series.isna() | (series.astype(str).str.strip() == "")


def normalize_scalar(text_normalizer, value: Any) -> Any:
    if pd.isna(value):
        return value
    return text_normalizer.normalize_scalar(value)
