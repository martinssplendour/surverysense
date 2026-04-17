from __future__ import annotations

from typing import Any

import pandas as pd

from app.services.cleaning_services._patterns import SMART_APOSTROPHES_PATTERN


class TextNormalizationService:
    """Shared text normalization for muddy survey exports."""

    def normalize_scalar(self, value: Any) -> Any:
        if value is None or pd.isna(value):
            return None
        text = str(value).replace("\ufeff", "")
        text = SMART_APOSTROPHES_PATTERN.sub("'", text)
        text = text.strip().rstrip("'").strip()
        return text

    def clean_series(self, col: pd.Series) -> pd.Series:
        """Vectorised equivalent of col.map(normalize_scalar)."""
        null_mask = col.isna()
        text = col.where(~null_mask, "").astype(str)
        text = text.str.replace("\ufeff", "", regex=False)
        text = text.str.replace(SMART_APOSTROPHES_PATTERN.pattern, "'", regex=True)
        text = text.str.strip().str.rstrip("'").str.strip()
        return text.where(~null_mask, other=None)

    def clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame(
            {col_name: self.clean_series(df[col_name]) for col_name in df.columns},
            index=df.index,
        )


class NullScrubbingService:
    def scrub_dataframe(self, df: pd.DataFrame, null_equivalents: list[str]) -> pd.DataFrame:
        normalized_nulls = {self._normalize_token(item) for item in null_equivalents}
        normalized_nulls.update({"", "nan", "<na>"})

        cleaned = {}
        for col_name in df.columns:
            col = df[col_name]
            null_mask = col.isna()
            # Normalise each value to its stripped/casefolded token, then check membership.
            token = col.where(~null_mask, "").astype(str).str.strip().str.casefold()
            is_null = null_mask | token.isin(normalized_nulls)
            # Preserve the original (non-stringified) value for survivors.
            cleaned[col_name] = col.where(~is_null, other=None)
        return pd.DataFrame(cleaned, index=df.index)

    @staticmethod
    def _normalize_token(value: Any) -> str:
        return str(value).strip().casefold()
