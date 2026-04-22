from __future__ import annotations

import json
from typing import Any

from app.models.enums import AnalysisModelKey
from app.services.topic_analysis_services.contracts import TopicLabelEvidenceGroup


class TopicLabelPromptBuilder:
    @staticmethod
    def build_prompt(
        groups: list[TopicLabelEvidenceGroup],
        *,
        model_key: AnalysisModelKey,
        text_column_name: str,
    ) -> str:
        evidence_blob = json.dumps(
            {
                "analysis_mode": model_key.value,
                "text_column_name": text_column_name,
                "groups": [group.to_prompt_payload() for group in groups],
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
            "- Use examples and context_phrases as the main evidence.\n"
            "- Preserve useful qualifiers from context_phrases, such as Too Expensive instead of Expensive.\n"
            "- Do not use quotes, numbering, or explanations.\n"
            "- Current labels are weak hints only.\n"
            "- If a group is genuinely noisy, use Mixed or Unclear Responses.\n\n"
            f"Evidence:{evidence_blob}"
        )

    @staticmethod
    def gemini_response_schema() -> dict[str, Any]:
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
