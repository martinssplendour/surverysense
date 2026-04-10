from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from typing import Literal
from uuid import uuid4

import pandas as pd

from app.services.cleaning_services import AnalysisReadyDatasetService
from app.services.metadata_filter_service import MetadataFilterDefinition, MetadataFilterService


DatasetName = Literal["transformed", "analysis"]


@dataclass(slots=True)
class StoredResultDatasets:
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


class ResultNotFoundError(KeyError):
    """Raised when a stored transformation result is unavailable."""


class ResultStoreService:
    """In-memory storage for transformed datasets to support row paging."""

    def __init__(
        self,
        metadata_filter_service: MetadataFilterService,
        *,
        analysis_ready_service: AnalysisReadyDatasetService,
        max_results: int = 8,
    ) -> None:
        self.metadata_filter_service = metadata_filter_service
        self.analysis_ready_service = analysis_ready_service
        self.max_results = max_results
        self._results: OrderedDict[str, StoredResultDatasets] = OrderedDict()
        self._lock = Lock()

    def save(
        self,
        transformed_df: pd.DataFrame,
        analysis_df: pd.DataFrame,
        *,
        metadata_columns: list[str],
        verbatim_columns: list[str],
    ) -> str:
        result_id = uuid4().hex
        stored = StoredResultDatasets(
            transformed_df=transformed_df.copy(),
            analysis_df=analysis_df.copy(),
            metadata_columns=list(metadata_columns),
            verbatim_columns=list(verbatim_columns),
            available_filters=self.metadata_filter_service.build_definitions(
                transformed_df,
                metadata_columns=metadata_columns,
            ),
        )

        with self._lock:
            self._results[result_id] = stored
            self._results.move_to_end(result_id)
            while len(self._results) > self.max_results:
                self._results.popitem(last=False)

        return result_id

    def get_filters(self, result_id: str) -> list[MetadataFilterDefinition]:
        with self._lock:
            stored = self._results.get(result_id)

        if stored is None:
            raise ResultNotFoundError(f"No stored result exists for id '{result_id}'.")

        return stored.available_filters

    def update_column_role(
        self,
        result_id: str,
        *,
        column_name: str,
        role: Literal["metadata", "verbatim"],
    ) -> StoredResultDatasets:
        with self._lock:
            stored = self._results.get(result_id)
            if stored is None:
                raise ResultNotFoundError(f"No stored result exists for id '{result_id}'.")

            if column_name not in stored.transformed_df.columns:
                raise ValueError(f"Column '{column_name}' is not present in the transformed dataset.")

            metadata_columns = [column for column in stored.metadata_columns if column != column_name]
            verbatim_columns = [column for column in stored.verbatim_columns if column != column_name]
            if role == "metadata":
                metadata_columns.append(column_name)
            else:
                verbatim_columns.append(column_name)

            analysis_df, resolved_metadata, resolved_verbatim = self.analysis_ready_service.build_from_assignments(
                stored.transformed_df,
                metadata_columns=metadata_columns,
                verbatim_columns=verbatim_columns,
            )
            available_filters = self.metadata_filter_service.build_definitions(
                stored.transformed_df,
                metadata_columns=resolved_metadata,
            )

            stored.analysis_df = analysis_df
            stored.metadata_columns = resolved_metadata
            stored.verbatim_columns = resolved_verbatim
            stored.available_filters = available_filters
            self._results.move_to_end(result_id)
            return StoredResultDatasets(
                transformed_df=stored.transformed_df.copy(),
                analysis_df=stored.analysis_df.copy(),
                metadata_columns=list(stored.metadata_columns),
                verbatim_columns=list(stored.verbatim_columns),
                available_filters=list(stored.available_filters),
            )

    def get_dataset(
        self,
        result_id: str,
        *,
        dataset: DatasetName,
        filters: dict[str, list[str]] | None = None,
    ) -> StoredDatasetSelection:
        with self._lock:
            stored = self._results.get(result_id)

        if stored is None:
            raise ResultNotFoundError(f"No stored result exists for id '{result_id}'.")

        unfiltered_df = stored.transformed_df if dataset == "transformed" else stored.analysis_df
        filtered_df = self.metadata_filter_service.apply_filters(
            unfiltered_df,
            filters=filters,
            allowed_columns={definition.column_name for definition in stored.available_filters},
        )
        return StoredDatasetSelection(
            result_id=result_id,
            dataset=dataset,
            dataframe=filtered_df.copy(),
            total_row_count=int(len(unfiltered_df)),
            metadata_columns=list(stored.metadata_columns),
            verbatim_columns=list(stored.verbatim_columns),
        )

    def get_page(
        self,
        result_id: str,
        *,
        dataset: DatasetName,
        offset: int,
        limit: int,
        filters: dict[str, list[str]] | None = None,
    ) -> ResultRowsPage:
        if limit <= 0:
            raise ValueError("limit must be a positive integer.")

        with self._lock:
            stored = self._results.get(result_id)

        if stored is None:
            raise ResultNotFoundError(f"No stored result exists for id '{result_id}'.")

        selection = self.get_dataset(
            result_id,
            dataset=dataset,
            filters=filters,
        )
        unfiltered_df = stored.transformed_df if dataset == "transformed" else stored.analysis_df
        dataframe = selection.dataframe
        total_row_count = int(len(dataframe))
        unfiltered_row_count = int(len(unfiltered_df))
        normalized_offset = max(0, offset)
        page_df = dataframe.iloc[normalized_offset: normalized_offset + limit].copy()
        page_df = page_df.where(pd.notna(page_df), None)
        rows = page_df.to_dict(orient="records")

        return ResultRowsPage(
            result_id=result_id,
            dataset=dataset,
            total_row_count=total_row_count,
            unfiltered_row_count=unfiltered_row_count,
            offset=normalized_offset,
            limit=limit,
            has_more=(normalized_offset + len(rows)) < total_row_count,
            column_names=dataframe.columns.tolist(),
            rows=rows,
        )
