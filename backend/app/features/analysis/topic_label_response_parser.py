from __future__ import annotations

import re
from typing import Any


class TopicLabelResponseParser:
    @staticmethod
    def extract_gemini_text(response_json: dict[str, Any]) -> str:
        candidates = response_json.get("candidates", [])
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        text_parts = [str(part.get("text", "")) for part in parts if str(part.get("text", "")).strip()]
        return "\n".join(text_parts).strip()

    @staticmethod
    def parse_labels(payload: dict[str, Any], *, allowed_group_ids: set[str]) -> dict[str, str]:
        labels_by_group_id: dict[str, str] = {}
        for item in payload.get("labels", []):
            if not isinstance(item, dict):
                continue
            group_id = str(item.get("group_id", "")).strip()
            label = TopicLabelResponseParser.normalize_label(str(item.get("label", "")).strip())
            if not group_id or group_id not in allowed_group_ids or not label:
                continue
            labels_by_group_id[group_id] = label
        return labels_by_group_id

    @staticmethod
    def normalize_label(label: str) -> str:
        normalized = re.sub(r"\s+", " ", label).strip(" \t\r\n\"'`.,:;!?-")
        if not normalized:
            return ""
        return normalized[:80].rstrip()
