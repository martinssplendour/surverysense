"""Removes rows that have no non-null value in any verbatim column."""
from __future__ import annotations

import pandas as pd


class VerbatimRowFilterService:
    """Drops rows from the analysis DataFrame where every verbatim column is null or blank."""

    def drop_empty_rows(self, df: pd.DataFrame, verbatim_columns: list[str]) -> pd.DataFrame:
        """Return df with rows that are entirely blank across all verbatim_columns removed."""
        if not verbatim_columns:
            return df.reset_index(drop=True)
        mask = df[verbatim_columns].notna().any(axis=1)
        return df.loc[mask].reset_index(drop=True)
