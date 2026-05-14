"""Uses Gemini to generate concise English labels for topic-analysis groups via a structured JSON prompt."""
from __future__ import annotations

import json
import logging
import re
import socket
import time
import urllib.error
from collections.abc import Sequence
from dataclasses import dataclass

from app.features.analysis.gemini_topic_label_client import GeminiTopicLabelClient
from app.features.analysis.topic_analysis_services.contracts import (
    AnalysisGroupRecord,
    TopicLabelEvidenceGroup,
)
from app.features.analysis.topic_label_evidence_builder import TopicLabelEvidenceBuilder
from app.features.analysis.topic_label_prompt_builder import TopicLabelPromptBuilder
from app.features.analysis.topic_label_response_parser import TopicLabelResponseParser
from app.models.enums import AnalysisModelKey

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
    max_unigrams: int = 5
    max_bigrams: int = 3
    max_trigrams: int = 3
    min_ngram_document_count: int = 4
    batch_size: int = 5
    max_retries: int = 1
    retry_base_seconds: float = 0.75
    consolidate_similar_labels: bool = False


@dataclass(slots=True)
class TopicAiLabelingBatchResult:
    labels_by_group_id: dict[str, str]
    warnings: list[str]
    labeled_group_count: int


class TopicAiLabelService:
    """Calls Gemini to produce human-readable labels for clustered topic groups, falling back gracefully on any error."""

    GENERIC_LABELS = frozenset(
        {
            "feedback",
            "general feedback",
            "general responses",
            "general topics",
            "misc",
            "miscellaneous",
            "mixed",
            "mixed feedback",
            "other",
            "other feedback",
            "other responses",
            "responses",
            "survey feedback",
            "topic",
            "topics",
            "uncategorized",
            "unclear",
            "unclear feedback",
            "unclear responses",
            "unknown",
        }
    )
    PLACEHOLDER_TOKENS = frozenset(
        {
            "abc",
            "blah",
            "example",
            "foo",
            "ipsum",
            "lorem",
            "placeholder",
            "sample",
            "test",
            "todo",
            "tbd",
            "xxx",
        }
    )
    LABEL_TOKEN_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)

    def __init__(self, *, config: TopicAiLabelingConfig) -> None:
        self.config = config
        self.evidence_builder = TopicLabelEvidenceBuilder(
            max_groups=config.max_groups,
            max_examples_per_group=config.max_examples_per_group,
            max_terms_per_group=config.max_terms_per_group,
            max_chars_per_example=config.max_chars_per_example,
            max_unigrams=config.max_unigrams,
            max_bigrams=config.max_bigrams,
            max_trigrams=config.max_trigrams,
            min_ngram_document_count=config.min_ngram_document_count,
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
            logger.info(
                "AI topic labeling skipped: available=%s group_count=%s enabled=%s has_api_key=%s.",
                self.is_available(),
                len(groups),
                self.config.enabled,
                bool(self.config.gemini_api_key),
            )
            return TopicAiLabelingBatchResult(labels_by_group_id={}, warnings=[], labeled_group_count=0)

        evidence_groups = self._build_group_evidence(groups)
        if not evidence_groups:
            logger.info(
                "AI topic labeling skipped: no eligible evidence groups for model=%s column=%s input_group_count=%s.",
                model_key.value,
                text_column_name,
                len(groups),
            )
            return TopicAiLabelingBatchResult(labels_by_group_id={}, warnings=[], labeled_group_count=0)

        logger.info(
            "AI topic labeling started: model=%s column=%s evidence_group_count=%s batch_size=%s max_examples_per_group=%s.",
            model_key.value,
            text_column_name,
            len(evidence_groups),
            self.config.batch_size,
            self.config.max_examples_per_group,
        )
        labels_by_group_id: dict[str, str] = {}
        failed_group_count = 0
        rejected_label_count = 0
        consolidation_warnings: list[str] = []
        for evidence_batch in self._iter_batches(evidence_groups):
            try:
                batch_labels, batch_rejected_count = self._label_batch(
                    evidence_batch,
                    model_key=model_key,
                    text_column_name=text_column_name,
                )
            except Exception as exc:
                failed_group_count += len(evidence_batch)
                logger.warning(
                    "AI topic labeling batch was skipped for model=%s column=%s group_count=%s (%s: %s).",
                    model_key.value,
                    text_column_name,
                    len(evidence_batch),
                    type(exc).__name__,
                    exc,
                )
                continue
            labels_by_group_id.update(batch_labels)
            rejected_label_count += batch_rejected_count
            logger.info(
                "AI topic labeling batch completed: model=%s column=%s group_count=%s accepted_labels=%s rejected_labels=%s.",
                model_key.value,
                text_column_name,
                len(evidence_batch),
                len(batch_labels),
                batch_rejected_count,
            )

        labels_by_group_id, consolidation_warnings = self._consolidate_similar_labels(
            labels_by_group_id,
            groups=list(groups),
            model_key=model_key,
            text_column_name=text_column_name,
        )

        return TopicAiLabelingBatchResult(
            labels_by_group_id=labels_by_group_id,
            warnings=[
                *self._build_labeling_warnings(
                    failed_group_count=failed_group_count,
                    rejected_label_count=rejected_label_count,
                    total_group_count=len(evidence_groups),
                ),
                *consolidation_warnings,
            ],
            labeled_group_count=len(labels_by_group_id),
        )

    def _iter_batches(self, groups: list[TopicLabelEvidenceGroup]) -> list[list[TopicLabelEvidenceGroup]]:
        batch_size = max(1, int(self.config.batch_size or 1))
        return [groups[index : index + batch_size] for index in range(0, len(groups), batch_size)]

    def _label_batch(
        self,
        groups: list[TopicLabelEvidenceGroup],
        *,
        model_key: AnalysisModelKey,
        text_column_name: str,
    ) -> tuple[dict[str, str], int]:
        response_json = self._request_labels_with_retries(
            groups,
            model_key=model_key,
            text_column_name=text_column_name,
        )
        response_text = self._extract_gemini_text(response_json)
        if not response_text:
            raise ValueError("Gemini returned an empty label response.")
        payload = json.loads(response_text)
        if not isinstance(payload, dict):
            raise ValueError("Gemini label response was not a JSON object.")
        parsed_labels = self._parse_labels(
            payload,
            allowed_group_ids={item.group_id for item in groups},
        )
        return self._filter_valid_labels(parsed_labels, groups)

    @staticmethod
    def _build_labeling_warnings(
        *,
        failed_group_count: int,
        rejected_label_count: int,
        total_group_count: int,
    ) -> list[str]:
        warnings: list[str] = []
        if failed_group_count >= total_group_count:
            return ["AI topic labeling was skipped and heuristic labels were kept."]
        if failed_group_count > 0:
            warnings.append(
                "AI topic labeling was skipped for "
                f"{failed_group_count} group(s); heuristic labels were kept for those group(s)."
            )
        if rejected_label_count > 0:
            warnings.append(
                "AI topic labeling returned low-quality labels for "
                f"{rejected_label_count} group(s); heuristic labels were kept for those group(s)."
            )
        return warnings

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

    def _consolidate_similar_labels(
        self,
        labels_by_group_id: dict[str, str],
        *,
        groups: list[AnalysisGroupRecord],
        model_key: AnalysisModelKey,
        text_column_name: str,
    ) -> tuple[dict[str, str], list[str]]:
        if not self.config.consolidate_similar_labels or len(labels_by_group_id) < 2:
            logger.info(
                "AI topic label consolidation skipped: enabled=%s label_count=%s.",
                self.config.consolidate_similar_labels,
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
            response_json = self._request_label_consolidation_with_retries(
                topics,
                model_key=model_key,
                text_column_name=text_column_name,
            )
            response_text = self._extract_gemini_text(response_json)
            if not response_text:
                raise ValueError("Gemini returned an empty label consolidation response.")
            payload = json.loads(response_text)
            if not isinstance(payload, dict):
                raise ValueError("Gemini label consolidation response was not a JSON object.")
            canonical_labels = self._parse_label_consolidation(
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

    def _request_label_consolidation(
        self,
        topics: list[dict[str, object]],
        *,
        model_key: AnalysisModelKey,
        text_column_name: str,
    ) -> dict[str, object]:
        return self.client.request_label_consolidation(
            topics,
            model_key=model_key,
            text_column_name=text_column_name,
        )

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

    def _parse_label_consolidation(
        self,
        payload: dict[str, object],
        *,
        allowed_group_ids: set[str],
    ) -> dict[str, str]:
        canonical_by_group_id: dict[str, str] = {}
        for item in payload.get("merged_topics", []):
            if not isinstance(item, dict):
                continue
            canonical_label = self._normalize_label(str(item.get("canonical_label", "")).strip())
            if not canonical_label:
                continue
            raw_group_ids = item.get("group_ids", [])
            if not isinstance(raw_group_ids, list):
                continue
            group_ids = [str(group_id).strip() for group_id in raw_group_ids if str(group_id).strip() in allowed_group_ids]
            unique_group_ids = list(dict.fromkeys(group_ids))
            if len(unique_group_ids) < 2:
                continue
            tokens = self._label_tokens(canonical_label)
            if not self._has_reasonable_length(canonical_label, tokens):
                continue
            if self._normalize_for_validation(canonical_label) in self.GENERIC_LABELS:
                continue
            for group_id in unique_group_ids:
                canonical_by_group_id[group_id] = canonical_label
        return canonical_by_group_id

    def _filter_valid_labels(
        self,
        labels_by_group_id: dict[str, str],
        groups: list[TopicLabelEvidenceGroup],
    ) -> tuple[dict[str, str], int]:
        groups_by_id = {group.group_id: group for group in groups}
        valid_labels: dict[str, str] = {}
        rejected_count = 0
        for group_id, label in labels_by_group_id.items():
            group = groups_by_id.get(group_id)
            if group is None:
                continue
            if not self._is_valid_ai_label(label, group):
                rejected_count += 1
                logger.warning(
                    "AI topic label was rejected for group_id=%s label=%r; heuristic label was kept.",
                    group_id,
                    label,
                )
                continue
            valid_labels[group_id] = label
        return valid_labels, rejected_count

    def _is_valid_ai_label(self, label: str, group: TopicLabelEvidenceGroup) -> bool:
        normalized = self._normalize_for_validation(label)
        tokens = self._label_tokens(label)
        if not normalized or not tokens:
            return False
        if normalized in self.GENERIC_LABELS:
            return False
        if any(token in self.PLACEHOLDER_TOKENS for token in tokens):
            return False
        if self._has_excessive_repetition(tokens):
            return False
        if self._is_keyword_stitch_label(tokens):
            return False
        if not self._has_reasonable_length(label, tokens):
            return False
        if self._is_unsupported_generic_label(tokens, group):
            return False
        return True

    @classmethod
    def _is_keyword_stitch_label(cls, tokens: list[str]) -> bool:
        if len(tokens) < 3:
            return False
        if {"printed", "bound", "teacher"}.issubset(set(tokens)):
            return True
        return False

    @classmethod
    def _has_reasonable_length(cls, label: str, tokens: list[str]) -> bool:
        if len(tokens) < 3 or len(tokens) > 8:
            return False
        stripped = label.strip()
        return 4 <= len(stripped) <= 80

    @staticmethod
    def _has_excessive_repetition(tokens: list[str]) -> bool:
        unique_tokens = set(tokens)
        if len(unique_tokens) == 1 and len(tokens) > 1:
            return True
        if len(tokens) >= 4 and len(unique_tokens) <= 2:
            return True
        return False

    def _is_unsupported_generic_label(self, tokens: list[str], group: TopicLabelEvidenceGroup) -> bool:
        evidence_tokens = self._evidence_tokens(group)
        if not evidence_tokens:
            return False
        content_tokens = [token for token in tokens if token not in self.GENERIC_LABELS]
        if not content_tokens:
            return True
        matching_tokens = [token for token in content_tokens if token in evidence_tokens]
        return not matching_tokens and len(content_tokens) <= 2

    def _evidence_tokens(self, group: TopicLabelEvidenceGroup) -> set[str]:
        ngram_terms = [
            item.term
            for item in [*group.top_unigrams, *group.top_bigrams, *group.top_trigrams]
        ]
        ngram_documents = [
            document
            for item in [*group.top_bigrams, *group.top_trigrams]
            for document in item.documents
        ]
        evidence_parts = [
            *group.terms,
            *group.context_phrases,
            *ngram_terms,
            *ngram_documents,
            *group.tightest_responses,
        ]
        return {
            token
            for part in evidence_parts
            for token in self._label_tokens(part)
            if len(token) > 2
        }

    @classmethod
    def _label_tokens(cls, label: str) -> list[str]:
        return [token.casefold() for token in cls.LABEL_TOKEN_PATTERN.findall(str(label or ""))]

    @classmethod
    def _normalize_for_validation(cls, label: str) -> str:
        return " ".join(cls._label_tokens(label))

    def _request_labels_with_retries(
        self,
        groups: list[TopicLabelEvidenceGroup],
        *,
        model_key: AnalysisModelKey,
        text_column_name: str,
    ) -> dict[str, object]:
        max_attempts = max(1, int(self.config.max_retries) + 1)
        for attempt_index in range(max_attempts):
            try:
                return self._request_labels(
                    groups,
                    model_key=model_key,
                    text_column_name=text_column_name,
                )
            except Exception as exc:
                has_attempt_remaining = attempt_index < max_attempts - 1
                if not has_attempt_remaining or not self._is_retryable_error(exc):
                    raise

                logger.warning(
                    "AI topic labeling request failed transiently for model=%s column=%s; retrying attempt %s of %s (%s: %s).",
                    model_key.value,
                    text_column_name,
                    attempt_index + 2,
                    max_attempts,
                    type(exc).__name__,
                    exc,
                )
                delay = self._retry_delay_seconds(attempt_index)
                if delay > 0:
                    time.sleep(delay)

        raise RuntimeError("AI topic labeling retry loop ended without a response.")

    def _request_label_consolidation_with_retries(
        self,
        topics: list[dict[str, object]],
        *,
        model_key: AnalysisModelKey,
        text_column_name: str,
    ) -> dict[str, object]:
        max_attempts = max(1, int(self.config.max_retries) + 1)
        for attempt_index in range(max_attempts):
            try:
                return self._request_label_consolidation(
                    topics,
                    model_key=model_key,
                    text_column_name=text_column_name,
                )
            except Exception as exc:
                has_attempt_remaining = attempt_index < max_attempts - 1
                if not has_attempt_remaining or not self._is_retryable_error(exc):
                    raise

                logger.warning(
                    "AI topic label consolidation request failed transiently for model=%s column=%s; retrying attempt %s of %s (%s: %s).",
                    model_key.value,
                    text_column_name,
                    attempt_index + 2,
                    max_attempts,
                    type(exc).__name__,
                    exc,
                )
                delay = self._retry_delay_seconds(attempt_index)
                if delay > 0:
                    time.sleep(delay)

        raise RuntimeError("AI topic label consolidation retry loop ended without a response.")

    def _retry_delay_seconds(self, attempt_index: int) -> float:
        base_delay = max(0.0, float(self.config.retry_base_seconds))
        return base_delay * (2 ** max(0, int(attempt_index)))

    @staticmethod
    def _is_retryable_error(exc: Exception) -> bool:
        if isinstance(exc, (TimeoutError, socket.timeout)):
            return True
        if isinstance(exc, urllib.error.HTTPError):
            return int(exc.code) in {408, 429, 500, 502, 503, 504}
        if isinstance(exc, urllib.error.URLError):
            reason = getattr(exc, "reason", None)
            if isinstance(reason, (TimeoutError, socket.timeout)):
                return True
            return "timed out" in str(exc).casefold()
        return "timed out" in str(exc).casefold()

    def _normalize_label(self, label: str) -> str:
        return self.response_parser.normalize_label(label)
