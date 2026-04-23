from __future__ import annotations

import json
from typing import Any

from app.features.analysis.topic_analysis_services.contracts import TopicLabelEvidenceGroup
from app.models.enums import AnalysisModelKey


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
            "You are labelling topic clusters from a survey analysis. "
            "Each cluster groups semantically similar responses together.\n\n"
            "For each group, read all the examples and identify the single dominant theme "
            "shared across most of them. Return one specific, descriptive label per group_id.\n\n"
            "Rules:\n"
            "- Return exactly one label per group_id.\n"
            "- 2 to 6 words, Title Case, plain English.\n"
            "- Be specific: 'Slow Delivery Times' not 'Delivery'; 'App Login Errors' not 'Technical Issues'.\n"
            "- Capture consistent sentiment where it is clear: 'Poor Customer Support' not 'Customer Support'.\n"
            "- examples are the primary signal — base the label on what most of them share.\n"
            "- frequent_phrases shows vocabulary recurring across many responses in the cluster; "
            "use it to confirm the dominant topic or spot qualifiers like 'too expensive'.\n"
            "- terms are keyword hints from the topic model; heuristic_label is a weak fallback — override both freely.\n"
            "- If the examples genuinely cover multiple unrelated topics, label it 'Mixed Responses'.\n"
            "- No quotes, numbers, or explanations in the label.\n\n"
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
