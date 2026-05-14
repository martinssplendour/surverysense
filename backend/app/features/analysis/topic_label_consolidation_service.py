from __future__ import annotations

import json
import logging

from app.features.analysis.topic_analysis_services.contracts import AnalysisGroupRecord
from app.features.analysis.topic_label_validator import TopicLabelValidator
from app.models.enums import AnalysisModelKey

logger = logging.getLogger(__name__)


class TopicLabelConsolidationService:
    def __init__(
        self,
        *,
        enabled: bool,
        request_with_retries,
        extract_text,
        normalize_label,
        validator: TopicLabelValidator,
    ) -> None:
        self.enabled = enabled
        self.request_with_retries = request_with_retries
        self.extract_text = extract_text
        self.normalize_label = normalize_label
        self.validator = validator

    def consolidate(
        self,
        labels_by_group_id: dict[str, str],
        *,
        groups: list[AnalysisGroupRecord],
        model_key: AnalysisModelKey,
        text_column_name: str,
    ) -> tuple[dict[str, str], list[str]]:
        if not self.enabled or len(labels_by_group_id) < 2:
            logger.info(
                "AI topic label consolidation skipped: enabled=%s label_count=%s.",
                self.enabled,
                len(labels_by_group_id),
            )
            return labels_by_group_id, []

        groups_by_id = {str(group.group_id): group for group in groups}
        topics = [
            {
                "group_id": group_id,
                "label": label,
                "count": int(groups_by_id[group_id].count or 0),
                "is_noise": bool(groups_by_id[group_id].is_noise),
            }
            for group_id, label in labels_by_group_id.items()
            if group_id in groups_by_id and label.strip() and not groups_by_id[group_id].is_noise
        ]
        if len(topics) < 2:
            logger.info(
                "AI topic label consolidation skipped: eligible_non_noise_topic_count=%s.",
                len(topics),
            )
            return labels_by_group_id, []

        try:
            response_json = self.request_with_retries(
                topics,
                model_key=model_key,
                text_column_name=text_column_name,
            )
            response_text = self.extract_text(response_json)
            if not response_text:
                raise ValueError("Gemini returned an empty label consolidation response.")
            payload = json.loads(response_text)
            if not isinstance(payload, dict):
                raise ValueError("Gemini label consolidation response was not a JSON object.")
            canonical_labels = self.parse_label_consolidation(
                payload,
                allowed_group_ids={str(topic["group_id"]) for topic in topics},
            )
        except Exception as exc:
            logger.warning(
                "AI topic label consolidation was skipped for model=%s column=%s (%s: %s).",
                model_key.value,
                text_column_name,
                type(exc).__name__,
                exc,
            )
            return labels_by_group_id, ["AI topic label consolidation was skipped; generated labels were kept."]

        if not canonical_labels:
            logger.info(
                "AI topic label consolidation completed: model=%s column=%s eligible_topic_count=%s merged_group_count=0.",
                model_key.value,
                text_column_name,
                len(topics),
            )
            return labels_by_group_id, []

        consolidated = dict(labels_by_group_id)
        for group_id, canonical_label in canonical_labels.items():
            consolidated[group_id] = canonical_label
        logger.info(
            "AI topic label consolidation completed: model=%s column=%s eligible_topic_count=%s merged_group_count=%s.",
            model_key.value,
            text_column_name,
            len(topics),
            len(canonical_labels),
        )
        return consolidated, [f"AI consolidated similar labels for {len(canonical_labels)} group(s)."]

    def parse_label_consolidation(
        self,
        payload: dict[str, object],
        *,
        allowed_group_ids: set[str],
    ) -> dict[str, str]:
        canonical_by_group_id: dict[str, str] = {}
        for item in payload.get("merged_topics", []):
            if not isinstance(item, dict):
                continue
            canonical_label = self.normalize_label(str(item.get("canonical_label", "")).strip())
            if not canonical_label:
                continue
            raw_group_ids = item.get("group_ids", [])
            if not isinstance(raw_group_ids, list):
                continue
            group_ids = [str(group_id).strip() for group_id in raw_group_ids if str(group_id).strip() in allowed_group_ids]
            unique_group_ids = list(dict.fromkeys(group_ids))
            if len(unique_group_ids) < 2:
                continue
            tokens = self.validator.label_tokens(canonical_label)
            if not self.validator.has_reasonable_length(canonical_label, tokens):
                continue
            if self.validator.normalize_for_validation(canonical_label) in self.validator.GENERIC_LABELS:
                continue
            for group_id in unique_group_ids:
                canonical_by_group_id[group_id] = canonical_label
        return canonical_by_group_id
