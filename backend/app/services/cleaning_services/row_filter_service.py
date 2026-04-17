from __future__ import annotations

import pandas as pd


class VerbatimRowFilterService:
    def drop_empty_rows(self, df: pd.DataFrame, verbatim_columns: list[str]) -> pd.DataFrame:
        if not verbatim_columns:
            return df.reset_index(drop=True)
        mask = df[verbatim_columns].notna().any(axis=1)
        return df.loc[mask].reset_index(drop=True)
