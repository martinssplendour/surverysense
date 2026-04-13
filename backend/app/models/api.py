from __future__ import annotations

from typing import Literal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.manifest import TransformationManifest


class MetadataFilterOptionModel(BaseModel):
    value: str
    count: int


class MetadataFilterDefinitionModel(BaseModel):
    column_name: str
    display_name: str
    options: list[MetadataFilterOptionModel] = Field(default_factory=list)


class DiagnosticConfigResponse(BaseModel):
    ai_available: bool
    default_diagnostic_mode: Literal["ai", "rule_based"]
    architect_row_count: int


class UploadIngestResponse(BaseModel):
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
    dataset: Literal["transformed", "analysis"]
    total_row_count: int
    unfiltered_row_count: int
    offset: int
    limit: int
    has_more: bool
    column_names: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)


class ColumnRoleUpdateRequest(BaseModel):
    column_name: str
    role: Literal["metadata", "verbatim"]


class ColumnRoleUpdateResponse(BaseModel):
    result_id: str
    analysis_metadata_column_names: list[str] = Field(default_factory=list)
    analysis_verbatim_column_names: list[str] = Field(default_factory=list)
    analysis_row_count: int
    analysis_column_names: list[str] = Field(default_factory=list)
    available_filters: list[MetadataFilterDefinitionModel] = Field(default_factory=list)


class AnalysisRunRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    model_key: Literal["bertopic", "kmeans", "hdbscan", "ngrams"]
    text_column_name: str
    filters: dict[str, list[str]] = Field(default_factory=dict)


class AnalysisExampleModel(BaseModel):
    row_number: int
    text: str


class AnalysisGroupModel(BaseModel):
    group_id: str
    label: str
    comment: str
    count: int
    share: float
    terms: list[str] = Field(default_factory=list)
    examples: list[AnalysisExampleModel] = Field(default_factory=list)
    is_noise: bool = False


class AnalysisNgramItemModel(BaseModel):
    term: str
    count: int


class AnalysisNgramBucketModel(BaseModel):
    label: str
    ngram_size: int
    items: list[AnalysisNgramItemModel] = Field(default_factory=list)


class AnalysisScatterPointModel(BaseModel):
    row_number: int
    text: str
    group_id: str
    group_label: str
    x: float
    y: float


class AnalysisRunResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    ok: bool
    result_id: str
    model_key: Literal["bertopic", "kmeans", "hdbscan", "ngrams"]
    model_label: str
    text_column_name: str
    filtered_row_count: int
    valid_document_count: int
    skipped_document_count: int
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    groups: list[AnalysisGroupModel] = Field(default_factory=list)
    ngram_buckets: list[AnalysisNgramBucketModel] = Field(default_factory=list)
    scatter_points: list[AnalysisScatterPointModel] = Field(default_factory=list)
