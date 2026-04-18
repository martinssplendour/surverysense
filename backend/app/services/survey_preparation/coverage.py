from __future__ import annotations

from typing import Any

import pandas as pd

from app.services.survey_preparation._shared import is_blank


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
                .apply(lambda series: (~is_blank(series)).any())
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
