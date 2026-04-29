"""Pydantic request and response models for all ingest and analysis API endpoints."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AnalysisModelKey, ColumnRole
from app.models.manifest import TransformationManifest


class MetadataFilterOptionModel(BaseModel):
    """A single selectable value for a metadata filter, with its response count."""

    value: str
    count: int


class MetadataFilterDefinitionModel(BaseModel):
    """Describes one filterable metadata column and all its available option values."""

    column_name: str
    display_name: str
    options: list[MetadataFilterOptionModel] = Field(default_factory=list)


class DiagnosticConfigResponse(BaseModel):
    """Reports whether AI-based manifest diagnosis is configured and what mode will be used by default."""

    ai_available: bool
    default_diagnostic_mode: Literal["ai", "rule_based"]
    architect_row_count: int


class UploadIngestResponse(BaseModel):
    """Full response from a successful CSV upload: encoding, manifest, transformed and analysis dataset info."""

    result_id: str
    filename: str
    encoding: str
    raw_row_count: int
    raw_column_count: int
    sample_row_count: int
    architect_row_count: int
    column_index_map: dict[int, str]
    raw_sample_rows: list[dict[str, Any]] = Field(default_factory=list)
    manifest: TransformationManifest
    transformed_row_count: int
    transformed_column_names: list[str]
    transformed_preview_rows: list[dict[str, Any]] = Field(default_factory=list)
    analysis_metadata_column_names: list[str] = Field(default_factory=list)
    analysis_verbatim_column_names: list[str] = Field(default_factory=list)
    analysis_row_count: int
    analysis_column_names: list[str] = Field(default_factory=list)
    analysis_preview_rows: list[dict[str, Any]] = Field(default_factory=list)
    available_filters: list[MetadataFilterDefinitionModel] = Field(default_factory=list)


class ResultRowsResponse(BaseModel):
    result_id: str
    dataset: Literal["transformed", "analysis", "community_analysis"]
    total_row_count: int
    unfiltered_row_count: int
    offset: int
    limit: int
    has_more: bool
    column_names: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)


class ColumnRoleUpdateRequest(BaseModel):
    column_name: str
    role: ColumnRole


class ColumnRoleUpdateResponse(BaseModel):
    result_id: str
    analysis_metadata_column_names: list[str] = Field(default_factory=list)
    analysis_verbatim_column_names: list[str] = Field(default_factory=list)
    analysis_row_count: int
    analysis_column_names: list[str] = Field(default_factory=list)
    available_filters: list[MetadataFilterDefinitionModel] = Field(default_factory=list)


class AnalysisRunRequest(BaseModel):
    """Parameters for a topic-analysis run: which model to use, which column to analyse, and optional row filters."""

    model_config = ConfigDict(protected_namespaces=())
    model_key: AnalysisModelKey
    text_column_name: str
    filters: dict[str, list[str]] = Field(default_factory=dict)


class AnalysisExampleModel(BaseModel):
    row_number: int
    text: str
    source_text: str | None = None
    translated: bool = False


class AnalysisGroupDocumentModel(BaseModel):
    row_number: int
    text: str


class AnalysisGroupModel(BaseModel):
    group_id: str
    label: str
    source_label: str | None = None
    translated: bool = False
    ai_generated: bool = False
    comment: str
    count: int
    share: float
    terms: list[str] = Field(default_factory=list)
    examples: list[AnalysisExampleModel] = Field(default_factory=list)
    is_noise: bool = False


class AnalysisNgramItemModel(BaseModel):
    term: str
    source_term: str | None = None
    translated: bool = False
    count: int
    document_count: int = 0


class AnalysisNgramBucketModel(BaseModel):
    label: str
    ngram_size: int
    items: list[AnalysisNgramItemModel] = Field(default_factory=list)


class AnalysisScatterPointModel(BaseModel):
    point_index: int = -1
    row_number: int
    text: str
    source_text: str | None = None
    group_id: str
    group_label: str
    x: float
    y: float


class AnalysisNetworkEdgeModel(BaseModel):
    source_point_index: int | None = None
    target_point_index: int | None = None
    source_row_number: int
    target_row_number: int
    weight: float


class AnalysisRunResponse(BaseModel):
    """Complete result from a topic-analysis run, including groups, n-gram buckets, and plot data."""

    model_config = ConfigDict(protected_namespaces=())
    ok: bool
    result_id: str
    model_key: AnalysisModelKey
    model_label: str
    text_column_name: str
    filtered_row_count: int
    valid_document_count: int
    original_response_count: int = 0
    skipped_document_count: int
    translated_document_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    error_code: str | None = None
    retry_after_seconds: int | None = None
    groups: list[AnalysisGroupModel] = Field(default_factory=list)
    ngram_buckets: list[AnalysisNgramBucketModel] = Field(default_factory=list)
    scatter_points: list[AnalysisScatterPointModel] = Field(default_factory=list)
    network_edges: list[AnalysisNetworkEdgeModel] = Field(default_factory=list)


class AnalysisGroupDocumentsResponse(BaseModel):
    result_id: str
    group_id: str
    group_label: str
    text_column_name: str
    total_count: int
    offset: int
    limit: int
    has_more: bool
    documents: list[AnalysisGroupDocumentModel] = Field(default_factory=list)


class AnalysisNgramDocumentsResponse(BaseModel):
    result_id: str
    term: str
    source_term: str | None = None
    ngram_size: int
    text_column_name: str
    total_count: int
    hit_count: int
    offset: int
    limit: int
    has_more: bool
    documents: list[AnalysisGroupDocumentModel] = Field(default_factory=list)


class TranslateTextRequest(BaseModel):
    text: str


class TranslateTextResponse(BaseModel):
    original_text: str
    translated_text: str
    translated: bool = False
    warning: str | None = None


class AnalysisExportFilterModel(BaseModel):
    column_name: str
    display_name: str | None = None
    values: list[str] = Field(default_factory=list)


class AnalysisExportChartModel(BaseModel):
    title: str
    caption: str | None = None
    image_data_url: str


class AnalysisExportRequest(BaseModel):
    format: Literal["pdf", "docx", "pptx"]
    report_title: str
    source_filename: str | None = None
    subtitle: str | None = None
    active_filters: list[AnalysisExportFilterModel] = Field(default_factory=list)
    charts: list[AnalysisExportChartModel] = Field(default_factory=list)
    analysis_result: AnalysisRunResponse
