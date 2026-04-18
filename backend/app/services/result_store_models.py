"""Dataclasses shared by the in-memory result store and its helper services."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from app.services.metadata_filter_service import MetadataFilterDefinition


DatasetName = Literal["transformed", "analysis"]


@dataclass(slots=True)
class StoredResultDatasets:
    """Both DataFrames for one uploaded result, together with the resolved column role lists and filter definitions."""

    transformed_df: pd.DataFrame
    analysis_df: pd.DataFrame
    metadata_columns: list[str]
    verbatim_columns: list[str]
    available_filters: list[MetadataFilterDefinition]


@dataclass(slots=True)
class ResultRowsPage:
    result_id: str
    dataset: DatasetName
    total_row_count: int
    unfiltered_row_count: int
    offset: int
    limit: int
    has_more: bool
    column_names: list[str]
    rows: list[dict[str, object]]


@dataclass(slots=True)
class StoredDatasetSelection:
    result_id: str
    dataset: DatasetName
    dataframe: pd.DataFrame
    total_row_count: int
    metadata_columns: list[str]
    verbatim_columns: list[str]


@dataclass(slots=True)
class StoredAnalysisGroupSnapshot:
    group_id: str
    label: str
    count: int
    documents: list[dict[str, object]]
    meta: dict[str, object]


@dataclass(slots=True)
class StoredAnalysisNgramSnapshot:
    term: str
    source_term: str | None
    ngram_size: int
    hit_count: int
    documents: list[dict[str, object]]


@dataclass(slots=True)
class StoredAnalysisSnapshot:
    """Cached output of one analysis run, keyed per result_id, used to serve filter changes without re-running ML."""

    text_column_name: str
    model_key: str
    groups: dict[str, StoredAnalysisGroupSnapshot]
    ngram_items: dict[str, StoredAnalysisNgramSnapshot]
    scatter_points: list[dict[str, object]]


@dataclass(slots=True)
class AnalysisGroupDocumentsPage:
    result_id: str
    group_id: str
    group_label: str
    text_column_name: str
    total_count: int
    offset: int
    limit: int
    has_more: bool
    documents: list[dict[str, object]]


@dataclass(slots=True)
class AnalysisNgramDocumentsPage:
    result_id: str
    term: str
    source_term: str | None
    ngram_size: int
    text_column_name: str
    total_count: int
    hit_count: int
    offset: int
    limit: int
    has_more: bool
    documents: list[dict[str, object]]
