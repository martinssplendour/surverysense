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

    @staticmethod
    def build_label_consolidation_prompt(
        topics: list[dict[str, object]],
        *,
        model_key: AnalysisModelKey,
        text_column_name: str,
    ) -> str:
        topics_blob = json.dumps(
            {
                "analysis_mode": model_key.value,
                "text_column_name": text_column_name,
                "topics": topics,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return (
            "You are consolidating topic labels from a survey analysis.\n"
            "Decide which labels should be presented as the same final topic. "
            "Return only merge groups for labels that describe the same underlying user reason.\n\n"
            "Rules:\n"
            "- Merge labels when they are different wording for the same reason, concern, or feedback theme.\n"
            "- Merge differences in tense, audience, subscription type, timing, or phrasing when the core reason is the same.\n"
            "- Do not merge labels that are merely related but represent different causes.\n"
            "- Do not merge positive product feedback into a negative reason unless the main reason is the same.\n"
            "- Do not merge noise or unclear topics with clear topics.\n"
            "- Use a canonical_label that is 3 to 8 words, Title Case, plain English, and specific.\n"
            "- Omit topics that do not need merging.\n"
            "- Return JSON only.\n\n"
            "Examples:\n"
            "- Merge: 'Cannot Afford The Annual Subscription', 'Subscription Price Is Too Expensive', "
            "'Cannot Afford Personal Subscription Cost' -> 'Subscription Cost Is Too Expensive'.\n"
            "- Usually keep separate: 'Cannot Afford Subscription' and 'Removal Of Home Education Discount'.\n"
            "- Usually merge: 'Not Using Resources Enough For The Cost' and "
            "'Cannot Justify Subscription Cost For Usage' -> 'Low Usage Does Not Justify Cost'.\n\n"
            f"Topics:{topics_blob}"
        )

    @staticmethod
    def gemini_label_consolidation_response_schema() -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "merged_topics": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "canonical_label": {"type": "string"},
                            "group_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["canonical_label", "group_ids"],
                    },
                }
            },
            "required": ["merged_topics"],
        }
