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
            "For each group, read the phrase evidence and tightest responses, then identify "
            "the single dominant theme shared across most of them. Return one specific, descriptive label per group_id.\n\n"
            "Rules:\n"
            "- Return exactly one label per group_id.\n"
            "- 3 to 6 words, Title Case, plain English.\n"
            "- Be specific: 'Slow Delivery Times' not 'Delivery'; 'App Login Errors' not 'Technical Issues'.\n"
            "- Write natural human topic names, not a stitched list of keywords.\n"
            "- Prefer clear nouns such as Resources, Materials, Support, Search, Pricing, Content, Activities, Planning, or Usability when they fit the evidence.\n"
            "- Capture consistent sentiment where it is clear: 'Poor Customer Support' not 'Customer Support'.\n"
            "- top_bigrams and top_trigrams are the strongest phrase signals; each phrase includes count, document_count, and up to three matching documents.\n"
            "- tightest_responses are the most central responses in the cluster; base the label on what most of them share.\n"
            "- Use document_count as the stronger frequency signal when phrase counts disagree.\n"
            "- Ignore function words or connector words in any language, such as 'para', 'los', 'que', and 'las'.\n"
            "- Remove filler words such as 'Existing' or 'Proposed' unless they change the meaning.\n"
            "- If the evidence genuinely covers multiple unrelated topics, label it 'Mixed Responses'.\n"
            "- Never use placeholders or vague labels such as 'Blah Blah Blah', 'Other', 'Miscellaneous', 'General Feedback', or 'Responses'.\n"
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
