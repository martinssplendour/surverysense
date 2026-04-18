from __future__ import annotations

import itertools
from typing import Any

import numpy as np
import pandas as pd


class VerticalLayoutDetectionService:
    def __init__(self, *, column_stats_service, scoring_service) -> None:
        self.column_stats_service = column_stats_service
        self.scoring_service = scoring_service

    def detect_vertical_layout(self, df_sample: pd.DataFrame) -> dict[str, Any] | None:
        n_cols = df_sample.shape[1]
        if n_cols < 3 or df_sample.empty:
            return None

        col_stats = self.column_stats_service.precompute_column_stats(df_sample)
        candidate_cols = list(range(n_cols)) if n_cols <= 12 else self.column_stats_service.select_vertical_candidates(col_stats, top_k=7)

        best_candidate: dict[str, Any] | None = None
        best_rank = (0.0, 0.0)
        for record_key_idx, question_idx, answer_idx in itertools.permutations(candidate_cols, 3):
            candidate = self.score_vertical_candidate(
                df_sample,
                record_key_idx,
                question_idx,
                answer_idx,
                col_stats,
            )
            candidate_rank = (candidate["score"], col_stats[question_idx]["question_header_score"])
            if candidate_rank > best_rank:
                best_candidate = candidate
                best_rank = candidate_rank

        if not best_candidate or best_candidate["score"] < 6.5:
            return None

        question_header_indices = self.detect_question_header_indices(
            df_sample,
            primary_question_idx=best_candidate["question_col_idx"],
            exclude_indices={best_candidate["record_key_idx"], best_candidate["answer_col_idx"]},
            col_stats=col_stats,
        )
        helper_indices = self.detect_helper_indices(
            df_sample,
            exclude_indices=set(question_header_indices) | {best_candidate["record_key_idx"], best_candidate["answer_col_idx"]},
        )
        excluded = set(question_header_indices) | set(helper_indices) | {best_candidate["answer_col_idx"]}
        metadata_indices = [idx for idx in range(n_cols) if idx not in excluded]

        return {
            "record_key_indices": [best_candidate["record_key_idx"]],
            "question_header_indices": question_header_indices,
            "answer_col_idx": best_candidate["answer_col_idx"],
            "helper_indices": helper_indices,
            "metadata_indices": metadata_indices,
        }

    def score_vertical_candidate(
        self,
        df_sample: pd.DataFrame,
        record_key_idx: int,
        question_idx: int,
        answer_idx: int,
        col_stats: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if col_stats is not None:
            stats_rk = col_stats[record_key_idx]
            stats_q = col_stats[question_idx]
            stats_a = col_stats[answer_idx]

            combined = stats_rk["clean_mask_arr"] & stats_q["clean_mask_arr"] & stats_a["clean_mask_arr"]
            n_valid = int(np.count_nonzero(combined))
            if n_valid < 3:
                return {
                    "score": 0.0,
                    "record_key_idx": record_key_idx,
                    "question_col_idx": question_idx,
                    "answer_col_idx": answer_idx,
                }

            row_count = float(n_valid)
            rk_vals = stats_rk["clean_str_arr"][combined]
            q_vals = stats_q["clean_str_arr"][combined]
            a_vals = stats_a["clean_str_arr"][combined]

            rk_list = rk_vals.tolist()
            q_list = q_vals.tolist()
            record_key_unique = len(set(rk_list))
            question_unique = len(set(q_list))
            answer_unique = len(set(a_vals.tolist()))
            pair_unique = len(set(zip(rk_list, q_list)))

            avg_question_length = stats_q["avg_length"]
            avg_answer_length = stats_a["avg_length"]
            record_key_identifier_ratio = stats_rk["identifier_ratio"]
            answer_identifier_ratio = stats_a["identifier_ratio"]
            question_identifier_ratio = stats_q["identifier_ratio"]

            score = 0.0
            if record_key_unique and row_count / record_key_unique >= 1.5:
                score += 2.0
            if pair_unique / row_count >= 0.7:
                score += 1.0
            if question_unique and row_count / question_unique >= 1.2:
                score += 1.0
            if answer_unique >= question_unique:
                score += 0.5
            if avg_question_length >= 6.0:
                score += 1.0
            if avg_answer_length >= 2.0:
                score += 0.5
            if avg_answer_length >= avg_question_length:
                score += 0.5
            if record_key_identifier_ratio >= 0.6:
                score += 1.0
            if answer_identifier_ratio >= 0.6:
                score -= 3.0
            if question_identifier_ratio >= 0.2:
                score -= 2.0

            score += stats_rk["record_key_header_score"] * 2.0
            score += stats_q["question_header_name_score"]
            score += stats_a["answer_header_score"] * 1.5
            score -= stats_rk["helper_penalty"] * 2.0
            score -= stats_a["helper_penalty"] * 1.5

            return {
                "score": score,
                "record_key_idx": record_key_idx,
                "question_col_idx": question_idx,
                "answer_col_idx": answer_idx,
            }

        subset = df_sample.iloc[:, [record_key_idx, question_idx, answer_idx]].copy()
        subset.columns = ["record_key", "question_value", "answer_value"]
        subset = subset.apply(
            lambda col: col.map(
                lambda value: None if pd.isna(value) or str(value).strip() == "" else str(value).strip()
            )
        )
        subset = subset.dropna(subset=["record_key", "question_value", "answer_value"], how="any")
        if len(subset) < 3:
            return {
                "score": 0.0,
                "record_key_idx": record_key_idx,
                "question_col_idx": question_idx,
                "answer_col_idx": answer_idx,
            }

        row_count = float(len(subset))
        record_key_unique = subset["record_key"].nunique(dropna=True)
        question_unique = subset["question_value"].nunique(dropna=True)
        answer_unique = subset["answer_value"].nunique(dropna=True)
        pair_unique = subset[["record_key", "question_value"]].drop_duplicates().shape[0]
        avg_question_length = subset["question_value"].str.len().mean()
        avg_answer_length = subset["answer_value"].str.len().mean()
        record_key_header = str(df_sample.columns[record_key_idx])
        question_header = str(df_sample.columns[question_idx])
        answer_header = str(df_sample.columns[answer_idx])
        record_key_identifier_ratio = self.scoring_service.identifier_like_ratio(subset["record_key"])
        answer_identifier_ratio = self.scoring_service.identifier_like_ratio(subset["answer_value"])
        question_identifier_ratio = self.scoring_service.identifier_like_ratio(subset["question_value"])

        score = 0.0
        if record_key_unique and row_count / record_key_unique >= 1.5:
            score += 2.0
        if pair_unique / row_count >= 0.7:
            score += 1.0
        if question_unique and row_count / question_unique >= 1.2:
            score += 1.0
        if answer_unique >= question_unique:
            score += 0.5
        if avg_question_length >= 6.0:
            score += 1.0
        if avg_answer_length >= 2.0:
            score += 0.5
        if avg_answer_length >= avg_question_length:
            score += 0.5
        if record_key_identifier_ratio >= 0.6:
            score += 1.0
        if answer_identifier_ratio >= 0.6:
            score -= 3.0
        if question_identifier_ratio >= 0.2:
            score -= 2.0

        score += self.scoring_service.record_key_header_score(record_key_header) * 2.0
        score += self.scoring_service.question_header_name_score(question_header)
        score += self.scoring_service.answer_header_score(answer_header) * 1.5
        score -= self.scoring_service.helper_header_penalty(record_key_header) * 2.0
        score -= self.scoring_service.helper_header_penalty(answer_header) * 1.5

        return {
            "score": score,
            "record_key_idx": record_key_idx,
            "question_col_idx": question_idx,
            "answer_col_idx": answer_idx,
        }

    def detect_question_header_indices(
        self,
        df_sample: pd.DataFrame,
        *,
        primary_question_idx: int,
        exclude_indices: set[int],
        col_stats: list[dict[str, Any]] | None = None,
    ) -> list[int]:
        scored_columns: list[tuple[int, float]] = []
        for idx in range(df_sample.shape[1]):
            if idx in exclude_indices:
                continue
            score = (
                col_stats[idx]["question_header_score"]
                if col_stats is not None
                else self.scoring_service.score_question_header_column(df_sample.iloc[:, idx], str(df_sample.columns[idx]))
            )
            if score >= 2.0:
                scored_columns.append((idx, score))

        scored_columns.sort(key=lambda item: (-item[1], item[0]))
        ordered = [idx for idx, _ in scored_columns]
        if primary_question_idx not in ordered:
            ordered.insert(0, primary_question_idx)
        return ordered

    @staticmethod
    def detect_helper_indices(df_sample: pd.DataFrame, *, exclude_indices: set[int]) -> list[int]:
        helper_indices: list[int] = []
        for idx in range(df_sample.shape[1]):
            if idx in exclude_indices:
                continue
            header_name = str(df_sample.columns[idx]).strip().casefold()
            if any(token in header_name for token in {"question_order", "order", "sequence", "answer_number", "code", "rank", "position"}):
                helper_indices.append(idx)
        return sorted(set(helper_indices))
