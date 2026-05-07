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
            "You are labelling response groups from a survey analysis.\n"
            "For each group, prioritize the top terms as the main naming evidence, then use the top comments to confirm what those terms mean across the cluster. Identify the aggregate topic or topics shared across most responses and return a descriptive label per group_id.\n\n"
            "Rules:\n"
            "- Return a descriptive label per group_id.\n"
            "- 3 to 8 words, Title Case, plain English.\n"
            "- Be specific: 'Slow Delivery Times' not 'Delivery'; 'App Login Errors' not 'Technical Issues'.\n"
            "- Write natural human topic names, not a stitched list of keywords.\n"
            "- The label must be an aggregate of the responses, not a label for one standout comment.\n"
            "- The label must name the topic of the responses using only the supplied terms and top comments as evidence.\n"
            "- Build the label primarily from the strongest top terms when they accurately summarize the cluster.\n"
            "- Use the comments to avoid misleading labels when a top term has multiple meanings.\n"
            "- Prefer clear nouns such as Resources, Materials, Support, Search, Pricing, Content, Activities, Planning, or Usability when they fit the evidence.\n"
            "- Capture consistent sentiment where it is clear: 'Poor Customer Support' not 'Customer Support'.\n"
            "- Ignore function words or connector words in any language, such as 'para', 'los', 'que', and 'las'.\n"
            "- Remove filler words.\n"
            "- Never use placeholders or vague labels such as 'Blah Blah Blah', 'Other', 'Miscellaneous', 'General Feedback', or 'Responses'.\n"
            "- No quotes, numbers, or explanations in the label.\n"
            "- Check the generated label against the responses to make sure the label is a topic that those responses fall under and if not, regenerate a better one.\n\n"
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
