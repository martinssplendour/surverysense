"""Uses Gemini to generate concise English labels for topic-analysis groups via a structured JSON prompt."""
from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass

from app.models.enums import AnalysisModelKey
from app.features.analysis.gemini_topic_label_client import GeminiTopicLabelClient
from app.features.analysis.topic_analysis_services.contracts import (
    AnalysisGroupRecord,
    TopicLabelEvidenceGroup,
)
from app.features.analysis.topic_label_evidence_builder import TopicLabelEvidenceBuilder
from app.features.analysis.topic_label_prompt_builder import TopicLabelPromptBuilder
from app.features.analysis.topic_label_response_parser import TopicLabelResponseParser

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
        self.evidence_builder = TopicLabelEvidenceBuilder(
            max_groups=config.max_groups,
            max_examples_per_group=config.max_examples_per_group,
            max_terms_per_group=config.max_terms_per_group,
            max_chars_per_example=config.max_chars_per_example,
        )
        self.prompt_builder = TopicLabelPromptBuilder()
        self.client = GeminiTopicLabelClient(
            api_key=config.gemini_api_key,
            model=config.gemini_model,
            temperature=config.gemini_temperature,
            timeout_seconds=config.timeout_seconds,
            prompt_builder=self.prompt_builder,
        )
        self.response_parser = TopicLabelResponseParser()

    def is_available(self) -> bool:
        return self.config.enabled and bool(self.config.gemini_api_key)

    def label_groups(
        self,
        groups: Sequence[AnalysisGroupRecord],
        *,
        model_key: AnalysisModelKey,
        text_column_name: str,
    ) -> TopicAiLabelingBatchResult:
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
            if not isinstance(payload, dict):
                raise ValueError("Gemini label response was not a JSON object.")
            labels_by_group_id = self._parse_labels(
                payload,
                allowed_group_ids={item.group_id for item in evidence_groups},
            )
        except Exception as exc:
            logger.warning(
                "AI topic labeling was skipped for model=%s column=%s (%s: %s).",
                model_key.value,
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

    def _build_group_evidence(self, groups: Sequence[AnalysisGroupRecord]) -> list[TopicLabelEvidenceGroup]:
        return self.evidence_builder.build_group_evidence(list(groups))

    def _collect_examples(self, group: AnalysisGroupRecord) -> list[str]:
        return self.evidence_builder.collect_examples(group)

    def _collect_terms(self, group: AnalysisGroupRecord) -> list[str]:
        return self.evidence_builder.collect_terms(group)

    def _request_labels(
        self,
        groups: list[TopicLabelEvidenceGroup],
        *,
        model_key: AnalysisModelKey,
        text_column_name: str,
    ) -> dict[str, object]:
        response = self.client.request_labels(
            groups,
            model_key=model_key,
            text_column_name=text_column_name,
        )
        return response

    def _build_prompt(
        self,
        groups: list[TopicLabelEvidenceGroup],
        *,
        model_key: AnalysisModelKey,
        text_column_name: str,
    ) -> str:
        return self.prompt_builder.build_prompt(
            groups,
            model_key=model_key,
            text_column_name=text_column_name,
        )

    def _gemini_response_schema(self) -> dict[str, object]:
        return self.prompt_builder.gemini_response_schema()

    def _extract_gemini_text(self, response_json: dict[str, object]) -> str:
        return self.response_parser.extract_gemini_text(response_json)

    def _parse_labels(self, payload: dict[str, object], *, allowed_group_ids: set[str]) -> dict[str, str]:
        return self.response_parser.parse_labels(payload, allowed_group_ids=allowed_group_ids)

    def _normalize_label(self, label: str) -> str:
        return self.response_parser.normalize_label(label)
