from __future__ import annotations

import itertools
import json
import logging
import re
import urllib.request
from dataclasses import dataclass
from enum import Enum
from typing import Any

import pandas as pd

from app.core.exceptions import ManifestBuildError
from app.models.manifest import LayoutState, TransformationManifest


DEFAULT_NULL_EQUIVALENTS = ["", "n/a", "na", "none", "null", ".", "-", "<na>", "nan"]
IDENTIFIER_VALUE_PATTERN = re.compile(r"^[0-9a-f]{6,}(?:-[0-9a-f]{2,}){2,}$", re.IGNORECASE)
logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ManifestArchitectConfig:
    gemini_api_key: str
    gemini_model: str
    gemini_temperature: float
    gemini_timeout_seconds: int
    row_limit: int


class DiagnosticMode(str, Enum):
    AI = "ai"
    RULE_BASED = "rule_based"


class ManifestArchitectService:
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
        mode = diagnostic_mode or self.default_diagnostic_mode()
        logger.info(
            "Building transformation manifest with %s on %s sampled rows and %s columns.",
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
            except ManifestBuildError:
                raise
            except Exception as exc:
                raise ManifestBuildError(f"AI diagnosis failed: {exc}") from exc
        return self._build_manifest_heuristically(df_sample, column_index_map)

    def _build_manifest_with_gemini(
        self,
        df_sample: pd.DataFrame,
        column_index_map: dict[int, str],
    ) -> TransformationManifest:
        endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.config.gemini_model}:generateContent?key={self.config.gemini_api_key}"
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
            headers={"Content-Type": "application/json"},
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
            "AI diagnosis completed with layout=%s and source=%s.",
            manifest.layout_state,
            manifest.diagnostic_source,
        )
        return manifest

    def _build_manifest_heuristically(
        self,
        df_sample: pd.DataFrame,
        column_index_map: dict[int, str],
    ) -> TransformationManifest:
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
                "Rule-based diagnosis completed with layout=%s and source=%s.",
                manifest.layout_state,
                manifest.diagnostic_source,
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
            "Rule-based diagnosis completed with layout=%s and source=%s.",
            manifest.layout_state,
            manifest.diagnostic_source,
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
        rows: list[list[Any]] = []
        for _, row in df_sample.iterrows():
            rows.append([
                None if pd.isna(value) else value
                for value in row.tolist()
            ])
        return rows

    def _detect_vertical_layout(self, df_sample: pd.DataFrame) -> dict[str, Any] | None:
        n_cols = df_sample.shape[1]
        if n_cols < 3 or df_sample.empty:
            return None

        best_candidate: dict[str, Any] | None = None
        best_rank = (0.0, 0.0)
        for record_key_idx, question_idx, answer_idx in itertools.permutations(range(n_cols), 3):
            candidate = self._score_vertical_candidate(df_sample, record_key_idx, question_idx, answer_idx)
            question_header_score = self._score_question_header_column(
                df_sample.iloc[:, question_idx],
                str(df_sample.columns[question_idx]),
            )
            candidate_rank = (candidate["score"], question_header_score)
            if candidate_rank > best_rank:
                best_candidate = candidate
                best_rank = candidate_rank

        if not best_candidate or best_candidate["score"] < 6.5:
            return None

        question_header_indices = self._detect_question_header_indices(
            df_sample,
            primary_question_idx=best_candidate["question_col_idx"],
            exclude_indices={best_candidate["record_key_idx"], best_candidate["answer_col_idx"]},
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
    ) -> dict[str, Any]:
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
    ) -> list[int]:
        scored_columns: list[tuple[int, float]] = []
        for idx in range(df_sample.shape[1]):
            if idx in exclude_indices:
                continue
            score = self._score_question_header_column(df_sample.iloc[:, idx], str(df_sample.columns[idx]))
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
        non_blank = series[
            series.notna() & series.astype(str).map(lambda value: str(value).strip() != "")
        ]
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
        non_blank = series[
            series.notna() & series.astype(str).map(lambda value: str(value).strip() != "")
        ]
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
        if series.empty:
            return 0.0

        def looks_like_identifier(value: str) -> bool:
            text = str(value).strip()
            if not text or " " in text:
                return False
            if IDENTIFIER_VALUE_PATTERN.fullmatch(text):
                return True
            has_digit = any(char.isdigit() for char in text)
            has_alpha = any(char.isalpha() for char in text)
            return len(text) >= 12 and has_digit and has_alpha and text.count("-") >= 1

        return float(series.astype(str).map(looks_like_identifier).mean())

    @staticmethod
    def _header_hint_score(header_name: str, tokens: set[str]) -> float:
        normalized = header_name.strip().casefold()
        return 1.0 if any(token in normalized for token in tokens) else 0.0
