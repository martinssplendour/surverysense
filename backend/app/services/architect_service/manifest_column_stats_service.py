from __future__ import annotations

from typing import Any

import pandas as pd


class ManifestColumnStatsService:
    def __init__(self, *, scoring_service) -> None:
        self.scoring_service = scoring_service

    def precompute_column_stats(self, df_sample: pd.DataFrame) -> list[dict[str, Any]]:
        stats_list: list[dict[str, Any]] = []
        for idx in range(df_sample.shape[1]):
            col = df_sample.iloc[:, idx]
            header = str(df_sample.columns[idx])
            str_col = col.where(col.notna(), "").astype(str).str.strip()
            clean_mask = col.notna() & (str_col != "")
            clean_vals = str_col[clean_mask]
            nunique = int(clean_vals.nunique()) if not clean_vals.empty else 0
            avg_length = float(clean_vals.str.len().mean()) if not clean_vals.empty else 0.0
            identifier_ratio = self.scoring_service.identifier_like_ratio(clean_vals)
            stats_list.append({
                "clean_mask": clean_mask,
                "clean_str": str_col,
                "clean_mask_arr": clean_mask.to_numpy(),
                "clean_str_arr": str_col.to_numpy(dtype=object),
                "nunique": nunique,
                "avg_length": avg_length,
                "identifier_ratio": identifier_ratio,
                "header": header,
                "question_header_score": self.scoring_service.score_question_header_column(col, header),
                "question_header_name_score": self.scoring_service.question_header_name_score(header),
                "record_key_header_score": self.scoring_service.record_key_header_score(header),
                "answer_header_score": self.scoring_service.answer_header_score(header),
                "helper_penalty": self.scoring_service.helper_header_penalty(header),
            })
        return stats_list

    def select_vertical_candidates(
        self,
        col_stats: list[dict[str, Any]],
        *,
        top_k: int,
    ) -> list[int]:
        all_indices = list(range(len(col_stats)))

        def rk_score(idx: int) -> float:
            s = col_stats[idx]
            return s["record_key_header_score"] * 2.0 + s["identifier_ratio"] * 2.0 - s["helper_penalty"] * 2.0

        def q_score(idx: int) -> float:
            s = col_stats[idx]
            return s["question_header_score"] + (1.0 if s["avg_length"] >= 8 else 0.0) - s["identifier_ratio"] * 2.0

        def a_score(idx: int) -> float:
            s = col_stats[idx]
            return (
                s["answer_header_score"] * 1.5
                + (1.0 if s["avg_length"] >= 2 else 0.0)
                - s["identifier_ratio"] * 3.0
                - s["helper_penalty"] * 1.5
            )

        rk_top = sorted(all_indices, key=rk_score, reverse=True)[:top_k]
        q_top = sorted(all_indices, key=q_score, reverse=True)[:top_k]
        a_top = sorted(all_indices, key=a_score, reverse=True)[:top_k]
        return sorted(set(rk_top) | set(q_top) | set(a_top))
