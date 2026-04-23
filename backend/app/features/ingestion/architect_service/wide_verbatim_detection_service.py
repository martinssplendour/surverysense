from __future__ import annotations

import pandas as pd


class WideVerbatimDetectionService:
    def __init__(self, *, scoring_service) -> None:
        self.scoring_service = scoring_service

    def detect_wide_verbatim_indices(self, df_sample: pd.DataFrame) -> list[int]:
        scored_columns: list[tuple[int, float]] = []
        for idx in range(df_sample.shape[1]):
            score = self.scoring_service.score_wide_verbatim_column(df_sample.iloc[:, idx], str(df_sample.columns[idx]))
            scored_columns.append((idx, score))

        verbatim_indices = [idx for idx, score in scored_columns if score >= 2.5]
        if verbatim_indices:
            return verbatim_indices
        return [max(scored_columns, key=lambda item: item[1])[0]]
