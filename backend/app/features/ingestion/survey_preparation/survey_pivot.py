from __future__ import annotations

import pandas as pd

from app.core.exceptions import ManifestBuildError
from app.features.ingestion.survey_preparation._shared import METADATA_COLUMNS


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
