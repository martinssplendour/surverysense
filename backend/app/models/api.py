from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.models.manifest import TransformationManifest


class UploadIngestResponse(BaseModel):
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
