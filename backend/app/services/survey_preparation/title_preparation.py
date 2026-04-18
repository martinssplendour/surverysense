from __future__ import annotations

import pandas as pd

from app.services.cleaning_services import TextNormalizationService
from app.services.survey_preparation._shared import is_blank, normalize_scalar


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
                .where(~is_blank(prepared["full_title"]), prepared["main_title"])
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

    def normalize_title(self, value):
        return normalize_scalar(self.text_normalizer, value)

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        prepared = df.copy()
        if "main_title_fixed" in prepared.columns:
            prepared["main_title_norm"] = prepared["main_title_fixed"].map(self.normalize_title)
        if "full_title_fixed" in prepared.columns:
            prepared["full_title_norm"] = prepared["full_title_fixed"].map(self.normalize_title)
        return prepared
