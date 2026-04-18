from __future__ import annotations

import itertools
import logging
import re
from typing import Any

import numpy as np
import pandas as pd

from app.models.manifest import LayoutState, TransformationManifest
from app.services.architect_service.config import (
    DEFAULT_NULL_EQUIVALENTS,
    ManifestArchitectConfig,
)


logger = logging.getLogger(__name__)


class HeuristicManifestDiagnosisService:
    def __init__(self, config: ManifestArchitectConfig) -> None:
        self.config = config

    def build_manifest(
        self,
        df_sample: pd.DataFrame,
        column_index_map: dict[int, str],
    ) -> TransformationManifest:
        vertical_candidate = self.detect_vertical_layout(df_sample)
        if vertical_candidate is not None:
            manifest = TransformationManifest(
                diagnostic_source="heuristic",
                layout_state=LayoutState.VERTICAL,
                metadata_indices=vertical_candidate["metadata_indices"],
                verbatim_indices=[],
                vertical_assembly={
                    "is_required": True,
                    "record_key_indices": vertical_candidate["record_key_indices"],
                    "question_header_indices": vertical_candidate["question_header_indices"],
                    "answer_col_idx": vertical_candidate["answer_col_idx"],
                    "helper_indices": vertical_candidate["helper_indices"],
                    "duplicate_resolution": "last_non_null",
                    "row_consolidation": "one_row_per_record",
                },
                null_equivalents=DEFAULT_NULL_EQUIVALENTS,
                row_limit=self.config.row_limit,
                notes=[
                    "Manifest generated using rule-based diagnosis.",
                    "Vertical layout detected from repeated respondent/question patterns.",
                ],
            )
            logger.info(
                "Rule-based diagnosis completed with layout=%s source=%s metadata_columns=%s question_headers=%s.",
                manifest.layout_state,
                manifest.diagnostic_source,
                len(manifest.metadata_indices),
                len(manifest.vertical_assembly.question_header_indices),
            )
            return manifest

        verbatim_indices = self.detect_wide_verbatim_indices(df_sample)
        metadata_indices = [idx for idx in column_index_map if idx not in set(verbatim_indices)]
        manifest = TransformationManifest(
            diagnostic_source="heuristic",
            layout_state=LayoutState.WIDE,
            metadata_indices=metadata_indices,
            verbatim_indices=verbatim_indices,
            vertical_assembly={"is_required": False},
            null_equivalents=DEFAULT_NULL_EQUIVALENTS,
            row_limit=self.config.row_limit,
            notes=[
                "Manifest generated using rule-based diagnosis.",
                "Wide layout assumed because no strong vertical verbatim signature was found.",
            ],
        )
        logger.info(
            "Rule-based diagnosis completed with layout=%s source=%s metadata_columns=%s verbatim_columns=%s.",
            manifest.layout_state,
            manifest.diagnostic_source,
            len(manifest.metadata_indices),
            len(manifest.verbatim_indices),
        )
        return manifest

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
            identifier_ratio = self.identifier_like_ratio(clean_vals)
            stats_list.append({
                "clean_mask": clean_mask,
                "clean_str": str_col,
                "clean_mask_arr": clean_mask.to_numpy(),
                "clean_str_arr": str_col.to_numpy(dtype=object),
                "nunique": nunique,
                "avg_length": avg_length,
                "identifier_ratio": identifier_ratio,
                "header": header,
                "question_header_score": self.score_question_header_column(col, header),
                "question_header_name_score": self.question_header_name_score(header),
                "record_key_header_score": self.record_key_header_score(header),
                "answer_header_score": self.answer_header_score(header),
                "helper_penalty": self.helper_header_penalty(header),
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

    def detect_vertical_layout(self, df_sample: pd.DataFrame) -> dict[str, Any] | None:
        n_cols = df_sample.shape[1]
        if n_cols < 3 or df_sample.empty:
            return None

        col_stats = self.precompute_column_stats(df_sample)
        candidate_cols = list(range(n_cols)) if n_cols <= 12 else self.select_vertical_candidates(col_stats, top_k=7)

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
        record_key_identifier_ratio = self.identifier_like_ratio(subset["record_key"])
        answer_identifier_ratio = self.identifier_like_ratio(subset["answer_value"])
        question_identifier_ratio = self.identifier_like_ratio(subset["question_value"])

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

        score += self.record_key_header_score(record_key_header) * 2.0
        score += self.question_header_name_score(question_header)
        score += self.answer_header_score(answer_header) * 1.5
        score -= self.helper_header_penalty(record_key_header) * 2.0
        score -= self.helper_header_penalty(answer_header) * 1.5

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
                else self.score_question_header_column(df_sample.iloc[:, idx], str(df_sample.columns[idx]))
            )
            if score >= 2.0:
                scored_columns.append((idx, score))

        scored_columns.sort(key=lambda item: (-item[1], item[0]))
        ordered = [idx for idx, _ in scored_columns]
        if primary_question_idx not in ordered:
            ordered.insert(0, primary_question_idx)
        return ordered

    def detect_helper_indices(self, df_sample: pd.DataFrame, *, exclude_indices: set[int]) -> list[int]:
        helper_indices: list[int] = []
        for idx in range(df_sample.shape[1]):
            if idx in exclude_indices:
                continue
            header_name = str(df_sample.columns[idx]).strip().casefold()
            if any(token in header_name for token in {"question_order", "order", "sequence", "answer_number", "code", "rank", "position"}):
                helper_indices.append(idx)
        return sorted(set(helper_indices))

    def detect_wide_verbatim_indices(self, df_sample: pd.DataFrame) -> list[int]:
        scored_columns: list[tuple[int, float]] = []
        for idx in range(df_sample.shape[1]):
            score = self.score_wide_verbatim_column(df_sample.iloc[:, idx], str(df_sample.columns[idx]))
            scored_columns.append((idx, score))

        verbatim_indices = [idx for idx, score in scored_columns if score >= 2.5]
        if verbatim_indices:
            return verbatim_indices
        return [max(scored_columns, key=lambda item: item[1])[0]]

    @staticmethod
    def score_wide_verbatim_column(series: pd.Series, header_name: str) -> float:
        non_blank = series[series.notna() & (series.astype(str).str.strip() != "")]
        if non_blank.empty:
            return 0.0

        text_values = non_blank.astype(str).str.strip()
        unique_ratio = text_values.nunique(dropna=True) / max(len(text_values), 1)
        avg_length = text_values.str.len().mean()
        long_text_ratio = (text_values.str.len() >= 20).mean()
        numeric_ratio = pd.to_numeric(text_values, errors="coerce").notna().mean()

        score = 0.0
        if avg_length >= 12:
            score += 1.0
        if long_text_ratio >= 0.25:
            score += 1.0
        if unique_ratio >= 0.4:
            score += 1.0
        if numeric_ratio <= 0.25:
            score += 1.0
        score += HeuristicManifestDiagnosisService.header_hint_score(
            header_name,
            {"answer", "response", "comment", "feedback", "verbatim", "text"},
        )
        return score

    @staticmethod
    def score_question_header_column(series: pd.Series, header_name: str) -> float:
        non_blank = series[series.notna() & (series.astype(str).str.strip() != "")]
        if non_blank.empty:
            return 0.0

        text_values = non_blank.astype(str).str.strip()
        avg_length = text_values.str.len().mean()
        score = 0.0
        if avg_length >= 8:
            score += 1.0
        if avg_length >= 20:
            score += 0.5

        return score + HeuristicManifestDiagnosisService.question_header_name_score(header_name)

    @staticmethod
    def question_header_name_score(header_name: str) -> float:
        normalized_header = header_name.strip().casefold()
        score = 0.0
        if "survey_title" in normalized_header or normalized_header in {"survey name", "survey_name"}:
            score -= 3.0
        if "full_title" in normalized_header:
            score += 2.5
        if "main_title" in normalized_header:
            score += 1.75
        if "sub_title" in normalized_header:
            score += 1.25
        if any(token in normalized_header for token in {"question_text", "question", "prompt", "item", "topic"}):
            score += 1.0
        return score

    @staticmethod
    def record_key_header_score(header_name: str) -> float:
        tokens = HeuristicManifestDiagnosisService.header_tokens(header_name)
        score = 0.0
        if "id" in tokens:
            score += 1.0
        if {"response", "id"} <= tokens:
            score += 1.5
        if {"user", "id"} <= tokens:
            score += 1.0
        if {"record", "id"} <= tokens or {"submission", "id"} <= tokens:
            score += 1.0
        if "respondent" in tokens:
            score += 0.75
        return score

    @staticmethod
    def answer_header_score(header_name: str) -> float:
        tokens = HeuristicManifestDiagnosisService.header_tokens(header_name)
        score = 0.0
        if "answer" in tokens:
            score += 1.0
        if "value" in tokens:
            score += 0.75
        if "response" in tokens and "id" not in tokens:
            score += 0.5
        if tokens & {"comment", "comments", "feedback", "verbatim", "text"}:
            score += 1.0
        if "id" in tokens:
            score -= 1.0
        return score

    @staticmethod
    def helper_header_penalty(header_name: str) -> float:
        tokens = HeuristicManifestDiagnosisService.header_tokens(header_name)
        return 1.0 if tokens & {"order", "sequence", "number", "code", "rank", "position"} else 0.0

    @staticmethod
    def header_tokens(header_name: str) -> set[str]:
        return {token for token in re.split(r"[_\W]+", header_name.casefold()) if token}

    @staticmethod
    def identifier_like_ratio(series: pd.Series) -> float:
        if series.empty:
            return 0.0
        text = series.astype(str).str.strip()
        nonempty = text != ""
        no_space = ~text.str.contains(" ", regex=False, na=False)
        pattern_hit = text.str.fullmatch(r"[0-9a-f]{6,}(?:-[0-9a-f]{2,}){2,}", case=False, na=False)
        long_enough = text.str.len() >= 12
        has_digit = text.str.contains(r"\d", regex=True, na=False)
        has_alpha = text.str.contains(r"[a-zA-Z]", regex=True, na=False)
        has_dash = text.str.count(r"-") >= 1
        fallback = no_space & long_enough & has_digit & has_alpha & has_dash
        is_identifier = nonempty & no_space & (pattern_hit | fallback)
        return float(is_identifier.mean())

    @staticmethod
    def header_hint_score(header_name: str, tokens: set[str]) -> float:
        normalized = header_name.strip().casefold()
        return 1.0 if any(token in normalized for token in tokens) else 0.0
