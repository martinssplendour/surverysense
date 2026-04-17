"""Builds a TransformationManifest from a CSV sample, using Gemini AI or rule-based heuristics."""
from __future__ import annotations

import itertools
import json
import logging
import re
import urllib.request
from typing import Any

import numpy as np
import pandas as pd

from app.core.exceptions import ManifestBuildError
from app.models.manifest import LayoutState, TransformationManifest
from app.services.architect_service.config import (
    DEFAULT_NULL_EQUIVALENTS,
    DiagnosticMode,
    ManifestArchitectConfig,
)

logger = logging.getLogger(__name__)


class ManifestArchitectService:
    """Diagnoses a survey CSV sample and produces a TransformationManifest describing its layout and columns."""

    def __init__(self, config: ManifestArchitectConfig) -> None:
        self.config = config

    def is_ai_available(self) -> bool:
        return bool(self.config.gemini_api_key)

    def default_diagnostic_mode(self) -> DiagnosticMode:
        return DiagnosticMode.AI if self.is_ai_available() else DiagnosticMode.RULE_BASED

    def get_transformation_manifest(
        self,
        df_sample: pd.DataFrame,
        column_index_map: dict[int, str],
        *,
        diagnostic_mode: DiagnosticMode | None = None,
    ) -> TransformationManifest:
        """Return a manifest for the given sample, falling back from AI to heuristics on any failure."""
        mode = diagnostic_mode or self.default_diagnostic_mode()
        logger.info(
            "Transformation manifest build started with mode=%s sampled_rows=%s sampled_columns=%s.",
            "AI diagnosis" if mode == DiagnosticMode.AI else "rule-based diagnosis",
            len(df_sample),
            len(column_index_map),
        )
        if mode == DiagnosticMode.AI:
            if not self.is_ai_available():
                raise ManifestBuildError(
                    "AI diagnosis is not configured on this server. Add GEMINI_API_KEY or switch to rule-based diagnosis."
                )
            try:
                return self._build_manifest_with_gemini(df_sample, column_index_map)
            except Exception as exc:
                logger.warning(
                    "AI diagnosis failed during manifest build (%s). Falling back to rule-based diagnosis.",
                    type(exc).__name__,
                )
                manifest = self._build_manifest_heuristically(df_sample, column_index_map)
                manifest.notes.append(
                    f"AI diagnosis failed — rule-based fallback used. Reason: {exc}"
                )
                return manifest
        return self._build_manifest_heuristically(df_sample, column_index_map)

    def _build_manifest_with_gemini(
        self,
        df_sample: pd.DataFrame,
        column_index_map: dict[int, str],
    ) -> TransformationManifest:
        endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.config.gemini_model}:generateContent"
        )

        request_payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": self._build_gemini_prompt(df_sample, column_index_map)}],
                }
            ],
            "generationConfig": {
                "temperature": self.config.gemini_temperature,
                "responseMimeType": "application/json",
                "responseSchema": self._gemini_response_schema(),
            },
        }
        payload = json.dumps(request_payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.config.gemini_api_key,
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.config.gemini_timeout_seconds) as response:
            response_json = json.loads(response.read().decode("utf-8"))

        text = self._extract_gemini_text(response_json)
        if not text:
            raise ManifestBuildError("Gemini returned an empty manifest response.")

        raw_manifest = json.loads(text)
        raw_manifest["diagnostic_source"] = "gemini"
        raw_manifest["row_limit"] = self.config.row_limit
        manifest = TransformationManifest.model_validate(raw_manifest)
        logger.info(
            "AI diagnosis completed with layout=%s source=%s metadata_columns=%s verbatim_columns=%s.",
            manifest.layout_state,
            manifest.diagnostic_source,
            len(manifest.metadata_indices),
            len(manifest.verbatim_indices),
        )
        return manifest

    def _build_manifest_heuristically(
        self,
        df_sample: pd.DataFrame,
        column_index_map: dict[int, str],
    ) -> TransformationManifest:
        """Detect layout type via scoring heuristics and produce a rule-based manifest without Gemini."""
        vertical_candidate = self._detect_vertical_layout(df_sample)
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
                len(manifest.vertical_assembly.get("question_header_indices", [])),
            )
            return manifest

        verbatim_indices = self._detect_wide_verbatim_indices(df_sample)
        metadata_indices = [
            idx for idx in column_index_map
            if idx not in set(verbatim_indices)
        ]
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

    def _build_gemini_prompt(
        self,
        df_sample: pd.DataFrame,
        column_index_map: dict[int, str],
    ) -> str:
        evidence = {
            "column_index_map": column_index_map,
            "sample_rows": self._serialize_rows(df_sample),
            "row_count": int(len(df_sample)),
            "column_count": int(df_sample.shape[1]),
        }
        evidence_blob = json.dumps(evidence, ensure_ascii=False, indent=2)
        return (
            "You are the Architect in a verbatim ingestion pipeline.\n"
            "Your job is to diagnose a muddy survey export and return a JSON transformation manifest.\n"
            "The downstream Builder is deterministic and index-driven. It will use only integer column indices from your manifest.\n"
            "Do not rely on header names at execution time. Use headers only as weak context while diagnosing the sample.\n\n"
            "Primary objective:\n"
            "- This is a verbatim app.\n"
            "- Identify the columns needed to produce a clean verbatim-ready dataframe.\n"
            "- If the file is vertical, the result should become one row per respondent or submission record.\n"
            "- In vertical files, repeated question rows must be consolidated so each respondent/submission has one answer per verbatim/question column.\n"
            "- The Builder has multiple services available; your manifest must tell it which columns to use for record keys, question headers, answer values, metadata preservation, and duplicate cleanup.\n\n"
            "How to classify the layout:\n"
            "- Choose WIDE when each row already looks like one respondent/submission and verbatim answers already sit across columns.\n"
            "- Choose VERTICAL when the same respondent/submission appears in multiple rows and each row looks like a question/answer record.\n"
            "- If a likely ID column repeats and there are separate question-like and answer-like columns, this is almost certainly VERTICAL.\n\n"
            "Manifest field rules:\n"
            "- metadata_indices: columns to preserve as metadata in the final cleaned dataframe.\n"
            "- verbatim_indices: only for WIDE layouts; these are the text-bearing columns that should survive.\n"
            "- For VERTICAL layouts, set vertical_assembly.is_required=true.\n"
            "- record_key_indices: the minimum stable key columns that define one respondent/submission row after consolidation.\n"
            "- question_header_indices: an ordered list of question/verbatim header source columns from best to fallback.\n"
            "- answer_col_idx: the column containing the actual answer values.\n"
            "- helper_indices: per-question helper/order/code columns that should not survive as metadata or verbatim columns.\n"
            "- duplicate_resolution must be 'last_non_null'.\n"
            "- row_consolidation must be 'one_row_per_record'.\n"
            "- Keep row_limit at 5000.\n\n"
            "Strict VERTICAL rules:\n"
            "- record_key_indices must use stable respondent/submission identifiers, not sparse descriptive metadata.\n"
            "- Prefer true response/submission/respondent/user IDs that repeat across question rows.\n"
            "- Use as few record key columns as necessary to avoid splitting one respondent across multiple rows.\n"
            "- question_header_indices should usually include the most complete human-readable question label first, then sensible fallbacks.\n"
            "- If columns resemble full_title, main_title, sub_title, question_text, prompt, or similar, include them in best-to-fallback order when useful.\n"
            "- Do NOT put question header columns or the answer column inside metadata_indices unless they are also genuinely needed elsewhere.\n"
            "- Do NOT put helper fields like question order, answer number, sequence, or per-question codes into metadata_indices or record_key_indices.\n"
            "- verbatim_indices must be an empty array for VERTICAL layouts because the verbatim columns will be created during consolidation.\n\n"
            "Null-equivalent rules:\n"
            "- Start from this safe baseline unless evidence clearly says otherwise: empty string, n/a, na, none, null, ., -, <na>, nan.\n"
            "- Add dataset-specific missing tokens only when they clearly mean missing data, for example 'Not Available'.\n"
            "- Do NOT treat valid answers as null just because they are short or categorical.\n\n"
            "Quality check before answering:\n"
            "- Ask: will this manifest let the Builder create one row per respondent/submission with one answer per question column?\n"
            "- Ask: did I choose the true record key, the best question header fallback order, and the real answer column?\n"
            "- Ask: did I isolate helper columns that should be dropped from the final cleaned frame?\n"
            "- Return JSON only, without markdown fences or commentary.\n\n"
            f"Evidence JSON:\n{evidence_blob}"
        )

    @staticmethod
    def _gemini_response_schema() -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "layout_state": {"type": "string", "enum": ["WIDE", "VERTICAL"]},
                "metadata_indices": {"type": "array", "items": {"type": "integer"}},
                "verbatim_indices": {"type": "array", "items": {"type": "integer"}},
                "vertical_assembly": {
                    "type": "object",
                    "properties": {
                        "is_required": {"type": "boolean"},
                        "record_key_indices": {"type": "array", "items": {"type": "integer"}},
                        "question_header_indices": {"type": "array", "items": {"type": "integer"}},
                        "answer_col_idx": {"type": "integer"},
                        "helper_indices": {"type": "array", "items": {"type": "integer"}},
                        "duplicate_resolution": {"type": "string", "enum": ["last_non_null"]},
                        "row_consolidation": {"type": "string", "enum": ["one_row_per_record"]},
                    },
                    "required": [
                        "is_required",
                        "record_key_indices",
                        "question_header_indices",
                        "answer_col_idx",
                        "helper_indices",
                        "duplicate_resolution",
                        "row_consolidation",
                    ],
                },
                "null_equivalents": {"type": "array", "items": {"type": "string"}},
                "row_limit": {"type": "integer"},
                "notes": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "layout_state",
                "metadata_indices",
                "verbatim_indices",
                "vertical_assembly",
                "null_equivalents",
                "row_limit",
                "notes",
            ],
        }

    @staticmethod
    def _extract_gemini_text(response_json: dict[str, Any]) -> str:
        candidates = response_json.get("candidates", [])
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        text_parts = [str(part.get("text", "")) for part in parts if str(part.get("text", "")).strip()]
        return "\n".join(text_parts).strip()

    @staticmethod
    def _serialize_rows(df_sample: pd.DataFrame) -> list[list[Any]]:
        # to_numpy with na_value=None converts NaN/NaT/pd.NA → None in one vectorised step,
        # which is substantially faster than iterrows for any non-trivial sample.
        return df_sample.to_numpy(dtype=object, na_value=None).tolist()

    # ------------------------------------------------------------------
    # Per-column stat cache — built once per heuristic manifest call so
    # the O(n³) permutation loop never recomputes the same series stats.
    # ------------------------------------------------------------------

    def _precompute_column_stats(self, df_sample: pd.DataFrame) -> list[dict[str, Any]]:
        """Return one stat-dict per column, computed once for the whole permutation loop."""
        stats_list: list[dict[str, Any]] = []
        for idx in range(df_sample.shape[1]):
            col = df_sample.iloc[:, idx]
            header = str(df_sample.columns[idx])
            # Strip to strings; keep "" where the original value was null/empty.
            str_col = col.where(col.notna(), "").astype(str).str.strip()
            clean_mask = col.notna() & (str_col != "")
            clean_vals = str_col[clean_mask]
            nunique = int(clean_vals.nunique()) if not clean_vals.empty else 0
            avg_length = float(clean_vals.str.len().mean()) if not clean_vals.empty else 0.0
            identifier_ratio = self._identifier_like_ratio(clean_vals)
            stats_list.append({
                "clean_mask": clean_mask,
                "clean_str": str_col,
                # Numpy copies used inside the O(n³) loop — avoids pandas Series
                # construction overhead on every permutation.
                "clean_mask_arr": clean_mask.to_numpy(),
                "clean_str_arr": str_col.to_numpy(dtype=object),
                "nunique": nunique,
                "avg_length": avg_length,
                "identifier_ratio": identifier_ratio,
                "header": header,
                # Pre-scored header signals — avoids re-calling these inside the loop.
                "question_header_score": self._score_question_header_column(col, header),
                "question_header_name_score": self._question_header_name_score(header),
                "record_key_header_score": self._record_key_header_score(header),
                "answer_header_score": self._answer_header_score(header),
                "helper_penalty": self._helper_header_penalty(header),
            })
        return stats_list

    def _select_vertical_candidates(
        self,
        col_stats: list[dict[str, Any]],
        *,
        top_k: int,
    ) -> list[int]:
        """Return the sorted union of the top-k columns scored for each vertical role.

        Reduces the permutation search space from O(n³) to O(k³) for wide datasets
        while keeping the candidates that matter for each role.
        """
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

    # ------------------------------------------------------------------
    # Layout detection
    # ------------------------------------------------------------------

    def _detect_vertical_layout(self, df_sample: pd.DataFrame) -> dict[str, Any] | None:
        """Return vertical layout column assignments if heuristic scoring reaches the confidence threshold (≥ 6.5), else None."""
        n_cols = df_sample.shape[1]
        if n_cols < 3 or df_sample.empty:
            return None

        # Build per-column stat cache once; avoids repeated DataFrame slicing and
        # series scanning inside the permutation loop.
        col_stats = self._precompute_column_stats(df_sample)

        # For small column counts try every combination; for wider datasets
        # pre-filter to the top-k candidates per role before permuting.
        # For wide CSVs (>12 cols), pre-filter to the top-7 candidates per vertical role
        # before the O(k³) permutation search to keep the total iterations under ~1000.
        _FULL_SEARCH_LIMIT = 12
        if n_cols <= _FULL_SEARCH_LIMIT:
            candidate_cols = list(range(n_cols))
        else:
            candidate_cols = self._select_vertical_candidates(col_stats, top_k=7)

        best_candidate: dict[str, Any] | None = None
        best_rank = (0.0, 0.0)
        for record_key_idx, question_idx, answer_idx in itertools.permutations(candidate_cols, 3):
            candidate = self._score_vertical_candidate(
                df_sample, record_key_idx, question_idx, answer_idx, col_stats
            )
            # question_header_score is already cached — no extra call needed here.
            candidate_rank = (candidate["score"], col_stats[question_idx]["question_header_score"])
            if candidate_rank > best_rank:
                best_candidate = candidate
                best_rank = candidate_rank

        if not best_candidate or best_candidate["score"] < 6.5:
            return None

        question_header_indices = self._detect_question_header_indices(
            df_sample,
            primary_question_idx=best_candidate["question_col_idx"],
            exclude_indices={best_candidate["record_key_idx"], best_candidate["answer_col_idx"]},
            col_stats=col_stats,
        )
        helper_indices = self._detect_helper_indices(
            df_sample,
            exclude_indices=set(question_header_indices)
            | {best_candidate["record_key_idx"], best_candidate["answer_col_idx"]},
        )
        excluded = set(question_header_indices) | set(helper_indices) | {best_candidate["answer_col_idx"]}
        metadata_indices = [
            idx for idx in range(n_cols)
            if idx not in excluded
        ]

        return {
            "record_key_indices": [best_candidate["record_key_idx"]],
            "question_header_indices": question_header_indices,
            "answer_col_idx": best_candidate["answer_col_idx"],
            "helper_indices": helper_indices,
            "metadata_indices": metadata_indices,
        }

    def _score_vertical_candidate(
        self,
        df_sample: pd.DataFrame,
        record_key_idx: int,
        question_idx: int,
        answer_idx: int,
        col_stats: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Score one (record_key, question, answer) column triple for vertical layout fitness.

        When col_stats is provided, uses precomputed numpy arrays to avoid per-permutation DataFrame overhead.
        """
        if col_stats is not None:
            # Fast path: use precomputed per-column statistics so we never slice
            # the DataFrame or call header-scoring functions inside the loop.
            stats_rk = col_stats[record_key_idx]
            stats_q = col_stats[question_idx]
            stats_a = col_stats[answer_idx]

            # Use numpy arrays — avoids pandas Series construction overhead on
            # every permutation iteration (boolean indexing, nunique, &-operator).
            combined = (
                stats_rk["clean_mask_arr"] & stats_q["clean_mask_arr"] & stats_a["clean_mask_arr"]
            )
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

            # len(set(...)) on a small list beats pandas nunique for typical sample sizes.
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
            # Key signal: the same respondent ID must repeat across multiple rows (ratio ≥ 1.5 rows/ID).
            if record_key_unique and row_count / record_key_unique >= 1.5:
                score += 2.0
            # Most (key, question) pairs should be unique — repeated pairs suggest a non-vertical layout.
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
            # If the "answer" column looks like identifiers, it is likely a code/ID column, not free text.
            if answer_identifier_ratio >= 0.6:
                score -= 3.0
            # Questions should be human-readable strings, not identifier-like tokens.
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

        # Original path — kept for callers that do not supply col_stats.
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
        record_key_identifier_ratio = self._identifier_like_ratio(subset["record_key"])
        answer_identifier_ratio = self._identifier_like_ratio(subset["answer_value"])
        question_identifier_ratio = self._identifier_like_ratio(subset["question_value"])

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

        score += self._record_key_header_score(record_key_header) * 2.0
        score += self._question_header_name_score(question_header)
        score += self._answer_header_score(answer_header) * 1.5
        score -= self._helper_header_penalty(record_key_header) * 2.0
        score -= self._helper_header_penalty(answer_header) * 1.5

        return {
            "score": score,
            "record_key_idx": record_key_idx,
            "question_col_idx": question_idx,
            "answer_col_idx": answer_idx,
        }

    def _detect_question_header_indices(
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
                else self._score_question_header_column(df_sample.iloc[:, idx], str(df_sample.columns[idx]))
            )
            if score >= 2.0:
                scored_columns.append((idx, score))

        scored_columns.sort(key=lambda item: (-item[1], item[0]))
        ordered = [idx for idx, _ in scored_columns]
        if primary_question_idx not in ordered:
            ordered.insert(0, primary_question_idx)
        return ordered

    def _detect_helper_indices(self, df_sample: pd.DataFrame, *, exclude_indices: set[int]) -> list[int]:
        helper_indices: list[int] = []
        for idx in range(df_sample.shape[1]):
            if idx in exclude_indices:
                continue
            header_name = str(df_sample.columns[idx]).strip().casefold()
            if any(
                token in header_name
                for token in {"question_order", "order", "sequence", "answer_number", "code", "rank", "position"}
            ):
                helper_indices.append(idx)
        return sorted(set(helper_indices))

    def _detect_wide_verbatim_indices(self, df_sample: pd.DataFrame) -> list[int]:
        """Score all columns for wide verbatim content and return those above the 2.5 threshold; falls back to the best column."""
        scored_columns: list[tuple[int, float]] = []
        for idx in range(df_sample.shape[1]):
            score = self._score_wide_verbatim_column(df_sample.iloc[:, idx], str(df_sample.columns[idx]))
            scored_columns.append((idx, score))

        verbatim_indices = [idx for idx, score in scored_columns if score >= 2.5]
        if verbatim_indices:
            return verbatim_indices
        return [max(scored_columns, key=lambda item: item[1])[0]]

    @staticmethod
    def _score_wide_verbatim_column(series: pd.Series, header_name: str) -> float:
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
        score += ManifestArchitectService._header_hint_score(
            header_name,
            {"answer", "response", "comment", "feedback", "verbatim", "text"},
        )
        return score

    @staticmethod
    def _score_question_header_column(series: pd.Series, header_name: str) -> float:
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

        return score + ManifestArchitectService._question_header_name_score(header_name)

    @staticmethod
    def _question_header_name_score(header_name: str) -> float:
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
        if any(
            token in normalized_header
            for token in {"question_text", "question", "prompt", "item", "topic"}
        ):
            score += 1.0
        return score

    @staticmethod
    def _record_key_header_score(header_name: str) -> float:
        tokens = ManifestArchitectService._header_tokens(header_name)
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
    def _answer_header_score(header_name: str) -> float:
        tokens = ManifestArchitectService._header_tokens(header_name)
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
    def _helper_header_penalty(header_name: str) -> float:
        tokens = ManifestArchitectService._header_tokens(header_name)
        return 1.0 if tokens & {"order", "sequence", "number", "code", "rank", "position"} else 0.0

    @staticmethod
    def _header_tokens(header_name: str) -> set[str]:
        return {
            token
            for token in re.split(r"[_\W]+", header_name.casefold())
            if token
        }

    @staticmethod
    def _identifier_like_ratio(series: pd.Series) -> float:
        """Return the fraction of non-blank values that match UUID/hash-like identifier patterns."""
        if series.empty:
            return 0.0
        text = series.astype(str).str.strip()
        nonempty = text != ""
        no_space = ~text.str.contains(" ", regex=False, na=False)
        # Primary check: UUID-style hex segments (e.g. "a1b2c3-4d-5e").
        # Fallback: long alphanumeric-with-dash strings that look like opaque IDs.
        pattern_hit = text.str.fullmatch(
            r"[0-9a-f]{6,}(?:-[0-9a-f]{2,}){2,}", case=False, na=False
        )
        long_enough = text.str.len() >= 12
        has_digit = text.str.contains(r"\d", regex=True, na=False)
        has_alpha = text.str.contains(r"[a-zA-Z]", regex=True, na=False)
        has_dash = text.str.count(r"-") >= 1
        fallback = no_space & long_enough & has_digit & has_alpha & has_dash
        is_identifier = nonempty & no_space & (pattern_hit | fallback)
        return float(is_identifier.mean())

    @staticmethod
    def _header_hint_score(header_name: str, tokens: set[str]) -> float:
        normalized = header_name.strip().casefold()
        return 1.0 if any(token in normalized for token in tokens) else 0.0
