from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.constants import MODEL_LABELS
from app.models.enums import AnalysisModelKey


@dataclass(slots=True)
class AnalysisDocumentRecord:
    row_number: int
    text: str

    def to_api_payload(self) -> dict[str, object]:
        return {
            "row_number": int(self.row_number),
            "text": self.text,
        }


@dataclass(slots=True)
class AnalysisExampleRecord(AnalysisDocumentRecord):
    source_text: str | None = None
    translated: bool = False

    def to_api_payload(self) -> dict[str, object]:
        payload = AnalysisDocumentRecord.to_api_payload(self)
        payload["source_text"] = self.source_text
        payload["translated"] = bool(self.translated)
        return payload


@dataclass(slots=True)
class TopicModelGroupDefinition:
    terms: list[str] = field(default_factory=list)
    is_noise: bool = False


@dataclass(slots=True)
class TopicModelRunResult:
    assignments: list[int]
    warnings: list[str] = field(default_factory=list)
    groups: dict[str, TopicModelGroupDefinition] = field(default_factory=dict)
    network_edges: list[tuple[int, int, float]] = field(default_factory=list)
    layout_positions: dict[int, tuple[float, float]] = field(default_factory=dict)


@dataclass(slots=True)
class AnalysisGroupRecord:
    group_id: str
    label: str
    source_label: str | None = None
    translated: bool = False
    ai_generated: bool = False
    comment: str = ""
    count: int = 0
    share: float = 0.0
    total_documents: int = 0
    terms: list[str] = field(default_factory=list)
    term_strengths: dict[str, float] = field(default_factory=dict)
    examples: list[AnalysisExampleRecord] = field(default_factory=list)
    is_noise: bool = False
    documents: list[AnalysisDocumentRecord] = field(default_factory=list)
    label_translation_warnings: list[str] = field(default_factory=list)

    def to_api_payload(self) -> dict[str, object]:
        return {
            "group_id": self.group_id,
            "label": self.label,
            "source_label": self.source_label,
            "translated": bool(self.translated),
            "ai_generated": bool(self.ai_generated),
            "comment": self.comment,
            "count": int(self.count),
            "share": float(self.share),
            "terms": list(self.terms),
            "term_strengths": dict(self.term_strengths),
            "examples": [example.to_api_payload() for example in self.examples],
            "is_noise": bool(self.is_noise),
        }

    def to_snapshot_payload(self) -> dict[str, object]:
        payload = self.to_api_payload()
        payload["_documents"] = [document.to_api_payload() for document in self.documents]
        if self.total_documents:
            payload["total_documents"] = int(self.total_documents)
        if self.label_translation_warnings:
            payload["_label_translation_warnings"] = list(self.label_translation_warnings)
        return payload


@dataclass(slots=True)
class AnalysisNgramItemRecord:
    term: str
    count: int
    source_term: str | None = None
    translated: bool = False
    document_count: int = 0
    documents: list[AnalysisDocumentRecord] = field(default_factory=list)

    def to_api_payload(self) -> dict[str, object]:
        return {
            "term": self.term,
            "source_term": self.source_term,
            "translated": bool(self.translated),
            "count": int(self.count),
            "document_count": int(self.document_count),
        }

    def to_snapshot_payload(self) -> dict[str, object]:
        payload = self.to_api_payload()
        payload["_documents"] = [document.to_api_payload() for document in self.documents]
        return payload


@dataclass(slots=True)
class AnalysisNgramBucketRecord:
    label: str
    ngram_size: int
    items: list[AnalysisNgramItemRecord] = field(default_factory=list)

    def to_api_payload(self) -> dict[str, object]:
        return {
            "label": self.label,
            "ngram_size": int(self.ngram_size),
            "items": [item.to_api_payload() for item in self.items],
        }

    def to_snapshot_payload(self) -> dict[str, object]:
        return {
            "label": self.label,
            "ngram_size": int(self.ngram_size),
            "items": [item.to_snapshot_payload() for item in self.items],
        }


@dataclass(slots=True)
class AnalysisScatterPointRecord:
    row_number: int
    text: str
    group_id: str
    group_label: str
    x: float
    y: float
    source_text: str | None = None
    point_index: int = -1

    def to_api_payload(self) -> dict[str, object]:
        return {
            "point_index": int(self.point_index),
            "row_number": int(self.row_number),
            "text": self.text,
            "source_text": self.source_text,
            "group_id": self.group_id,
            "group_label": self.group_label,
            "x": float(self.x),
            "y": float(self.y),
        }


@dataclass(slots=True)
class AnalysisNetworkEdgeRecord:
    source_row_number: int
    target_row_number: int
    weight: float
    source_point_index: int | None = None
    target_point_index: int | None = None

    def to_api_payload(self) -> dict[str, object]:
        return {
            "source_point_index": self.source_point_index,
            "target_point_index": self.target_point_index,
            "source_row_number": int(self.source_row_number),
            "target_row_number": int(self.target_row_number),
            "weight": float(self.weight),
        }


@dataclass(slots=True)
class AnalysisRunResult:
    ok: bool
    result_id: str
    model_key: AnalysisModelKey
    model_label: str
    text_column_name: str
    filtered_row_count: int
    valid_document_count: int = 0
    original_response_count: int = 0
    skipped_document_count: int = 0
    translated_document_count: int = 0
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    error_code: str | None = None
    retry_after_seconds: int | None = None
    community_similarity_threshold: float | None = None
    groups: list[AnalysisGroupRecord] = field(default_factory=list)
    ngram_buckets: list[AnalysisNgramBucketRecord] = field(default_factory=list)
    scatter_points: list[AnalysisScatterPointRecord] = field(default_factory=list)
    network_edges: list[AnalysisNetworkEdgeRecord] = field(default_factory=list)

    @classmethod
    def empty(
        cls,
        *,
        result_id: str,
        model_key: AnalysisModelKey,
        text_column_name: str,
        filtered_row_count: int,
    ) -> AnalysisRunResult:
        return cls(
            ok=False,
            result_id=result_id,
            model_key=model_key,
            model_label=MODEL_LABELS[model_key],
            text_column_name=text_column_name,
            filtered_row_count=filtered_row_count,
        )

    def to_api_payload(self) -> dict[str, Any]:
        return {
            "ok": bool(self.ok),
            "result_id": self.result_id,
            "model_key": self.model_key.value,
            "model_label": self.model_label,
            "text_column_name": self.text_column_name,
            "filtered_row_count": int(self.filtered_row_count),
            "valid_document_count": int(self.valid_document_count),
            "original_response_count": int(self.original_response_count),
            "skipped_document_count": int(self.skipped_document_count),
            "translated_document_count": int(self.translated_document_count),
            "warnings": list(self.warnings),
            "error": self.error,
            "error_code": self.error_code,
            "retry_after_seconds": self.retry_after_seconds,
            "community_similarity_threshold": self.community_similarity_threshold,
            "groups": [group.to_api_payload() for group in self.groups],
            "ngram_buckets": [bucket.to_api_payload() for bucket in self.ngram_buckets],
            "scatter_points": [point.to_api_payload() for point in self.scatter_points],
            "network_edges": [edge.to_api_payload() for edge in self.network_edges],
        }

    def to_snapshot_payload(self) -> dict[str, Any]:
        payload = self.to_api_payload()
        payload["groups"] = [group.to_snapshot_payload() for group in self.groups]
        payload["ngram_buckets"] = [bucket.to_snapshot_payload() for bucket in self.ngram_buckets]
        return payload


@dataclass(slots=True)
class TopicLabelNgramEvidence:
    term: str
    count: int
    document_count: int
    documents: list[str] = field(default_factory=list)

    def to_prompt_payload(self) -> dict[str, object]:
        return {
            "term": self.term,
            "count": int(self.count),
            "document_count": int(self.document_count),
            "documents": list(self.documents),
        }


@dataclass(slots=True)
class TopicLabelEvidenceGroup:
    group_id: str
    current_label: str
    count: int
    share_percent: float
    terms: list[str] = field(default_factory=list)
    context_phrases: list[str] = field(default_factory=list)
    top_unigrams: list[TopicLabelNgramEvidence] = field(default_factory=list)
    top_bigrams: list[TopicLabelNgramEvidence] = field(default_factory=list)
    top_trigrams: list[TopicLabelNgramEvidence] = field(default_factory=list)
    tightest_responses: list[str] = field(default_factory=list)

    def to_prompt_payload(self) -> dict[str, object]:
        return {
            "group_id": self.group_id,
            "terms": list(self.terms),
            "top_comments": list(self.tightest_responses),
        }
