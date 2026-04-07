from __future__ import annotations

from typing import Literal
from typing import Any

from pydantic import BaseModel, Field

from app.models.manifest import TransformationManifest


class MetadataFilterOptionModel(BaseModel):
    value: str
    count: int


class MetadataFilterDefinitionModel(BaseModel):
    column_name: str
    display_name: str
    options: list[MetadataFilterOptionModel] = Field(default_factory=list)


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
