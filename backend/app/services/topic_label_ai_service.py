"""Uses Gemini to generate concise English labels for topic-analysis groups via a structured JSON prompt."""
from __future__ import annotations

import json
import logging
import re
import urllib.request
from dataclasses import dataclass
from typing import Any


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TopicAiLabelingConfig:
    enabled: bool
    gemini_api_key: str
    gemini_model: str
    gemini_temperature: float
    timeout_seconds: int
    max_groups: int
    max_examples_per_group: int
    max_terms_per_group: int
    max_chars_per_example: int


@dataclass(slots=True)
class TopicAiLabelingBatchResult:
    labels_by_group_id: dict[str, str]
    warnings: list[str]
    labeled_group_count: int


class TopicAiLabelService:
    """Calls Gemini to produce human-readable labels for clustered topic groups, falling back gracefully on any error."""

    def __init__(self, *, config: TopicAiLabelingConfig) -> None:
        self.config = config

    def is_available(self) -> bool:
        return self.config.enabled and bool(self.config.gemini_api_key)

    def label_groups(
        self,
        groups: list[dict[str, object]],
        *,
        model_key: str,
        text_column_name: str,
    ) -> TopicAiLabelingBatchResult:
        """Request AI-generated labels for up to max_groups non-noise groups; returns empty result on any failure."""
        if not self.is_available() or not groups:
            return TopicAiLabelingBatchResult(labels_by_group_id={}, warnings=[], labeled_group_count=0)

        evidence_groups = self._build_group_evidence(groups)
        if not evidence_groups:
            return TopicAiLabelingBatchResult(labels_by_group_id={}, warnings=[], labeled_group_count=0)

        try:
            response_json = self._request_labels(
                evidence_groups,
                model_key=model_key,
                text_column_name=text_column_name,
            )
            response_text = self._extract_gemini_text(response_json)
            if not response_text:
                raise ValueError("Gemini returned an empty label response.")
            payload = json.loads(response_text)
            labels_by_group_id = self._parse_labels(payload, allowed_group_ids={item["group_id"] for item in evidence_groups})
        except Exception as exc:
            logger.warning(
                "AI topic labeling was skipped for model=%s column=%s (%s: %s).",
                model_key,
                text_column_name,
                type(exc).__name__,
                exc,
            )
            return TopicAiLabelingBatchResult(
                labels_by_group_id={},
                warnings=["AI topic labeling was skipped and heuristic labels were kept."],
                labeled_group_count=0,
            )

        return TopicAiLabelingBatchResult(
            labels_by_group_id=labels_by_group_id,
            warnings=[],
            labeled_group_count=len(labels_by_group_id),
        )

    def _build_group_evidence(self, groups: list[dict[str, object]]) -> list[dict[str, object]]:
        """Assemble a trimmed evidence dict for each non-noise group to send to Gemini."""
        evidence_groups: list[dict[str, object]] = []
        for group in groups:
            if len(evidence_groups) >= max(1, self.config.max_groups):
                break
            if bool(group.get("is_noise")):
                continue

            group_id = str(group.get("group_id", "")).strip()
            if not group_id:
                continue

            examples = self._collect_examples(group)
            terms = self._collect_terms(group)
            evidence_groups.append(
                {
                    "group_id": group_id,
                    "current_label": str(group.get("label", "")).strip(),
                    "count": int(group.get("count", 0)),
                    "share_percent": round(float(group.get("share", 0.0)) * 100, 1),
                    "terms": terms,
                    "examples": examples,
                }
            )
        return evidence_groups

    def _collect_examples(self, group: dict[str, object]) -> list[str]:
        """Extract up to max_examples representative texts from a group, truncating each to max_chars."""
        examples: list[str] = []
        max_examples = max(1, self.config.max_examples_per_group)
        max_chars = max(80, self.config.max_chars_per_example)
        for example in group.get("examples", []):
            if not isinstance(example, dict):
                continue
            text = str(example.get("source_text") or example.get("text") or "").strip()
            if not text:
                continue
            normalized = re.sub(r"\s+", " ", text)
            examples.append(normalized[:max_chars].rstrip())
            if len(examples) >= max_examples:
                break
        return examples

    def _collect_terms(self, group: dict[str, object]) -> list[str]:
        terms: list[str] = []
        max_terms = max(1, self.config.max_terms_per_group)
        for term in group.get("terms", []):
            normalized = re.sub(r"\s+", " ", str(term).strip())
            if not normalized:
                continue
            terms.append(normalized)
            if len(terms) >= max_terms:
                break
        return terms

    def _request_labels(
        self,
        groups: list[dict[str, object]],
        *,
        model_key: str,
        text_column_name: str,
    ) -> dict[str, Any]:
        endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.config.gemini_model}:generateContent"
        )
        request_payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": self._build_prompt(
                                groups,
                                model_key=model_key,
                                text_column_name=text_column_name,
                            )
                        }
                    ],
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
        with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def _build_prompt(
        groups: list[dict[str, object]],
        *,
        model_key: str,
        text_column_name: str,
    ) -> str:
        evidence_blob = json.dumps(
            {
                "analysis_mode": model_key,
                "text_column_name": text_column_name,
                "groups": groups,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return (
            "Create concise English labels for clustered survey-response groups.\n"
            "Rules:\n"
            "- Return exactly one label per group_id.\n"
            "- 2 to 6 words.\n"
            "- Title case.\n"
            "- Plain English.\n"
            "- Prefer specific topic headings such as Curriculum Resources or Search Function Issues.\n"
            "- Do not use quotes, numbering, or explanations.\n"
            "- Current labels are weak hints only.\n"
            "- If a group is genuinely noisy, use Mixed or Unclear Responses.\n\n"
            f"Evidence:{evidence_blob}"
        )

    @staticmethod
    def _gemini_response_schema() -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "labels": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "group_id": {"type": "string"},
                            "label": {"type": "string"},
                        },
                        "required": ["group_id", "label"],
                    },
                }
            },
            "required": ["labels"],
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
    def _parse_labels(payload: dict[str, Any], *, allowed_group_ids: set[str]) -> dict[str, str]:
        labels_by_group_id: dict[str, str] = {}
        for item in payload.get("labels", []):
            if not isinstance(item, dict):
                continue
            group_id = str(item.get("group_id", "")).strip()
            label = TopicAiLabelService._normalize_label(str(item.get("label", "")).strip())
            if not group_id or group_id not in allowed_group_ids or not label:
                continue
            labels_by_group_id[group_id] = label
        return labels_by_group_id

    @staticmethod
    def _normalize_label(label: str) -> str:
        """Strip surrounding punctuation/whitespace from a Gemini label and cap it at 80 characters."""
        normalized = re.sub(r"\s+", " ", label).strip(" \t\r\n\"'`.,:;!?-")
        if not normalized:
            return ""
        return normalized[:80].rstrip()
