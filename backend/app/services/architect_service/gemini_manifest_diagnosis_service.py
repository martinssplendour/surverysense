from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any

import pandas as pd

from app.core.exceptions import ManifestBuildError
from app.models.manifest import TransformationManifest
from app.services.architect_service.config import ManifestArchitectConfig


logger = logging.getLogger(__name__)


class GeminiManifestDiagnosisService:
    def __init__(self, config: ManifestArchitectConfig) -> None:
        self.config = config

    def build_manifest(
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
                    "parts": [{"text": self.build_prompt(df_sample, column_index_map)}],
                }
            ],
            "generationConfig": {
                "temperature": self.config.gemini_temperature,
                "responseMimeType": "application/json",
                "responseSchema": self.response_schema(),
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

        text = self.extract_text(response_json)
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

    def build_prompt(
        self,
        df_sample: pd.DataFrame,
        column_index_map: dict[int, str],
    ) -> str:
        evidence = {
            "column_index_map": column_index_map,
            "sample_rows": self.serialize_rows(df_sample),
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
    def response_schema() -> dict[str, Any]:
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
    def extract_text(response_json: dict[str, Any]) -> str:
        candidates = response_json.get("candidates", [])
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        text_parts = [str(part.get("text", "")) for part in parts if str(part.get("text", "")).strip()]
        return "\n".join(text_parts).strip()

    @staticmethod
    def serialize_rows(df_sample: pd.DataFrame) -> list[list[Any]]:
        return df_sample.to_numpy(dtype=object, na_value=None).tolist()
