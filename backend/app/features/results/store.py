"""In-memory store for transformed datasets, analysis snapshots, and paged document retrieval."""
from __future__ import annotations

import logging
import re
from collections import OrderedDict
from numbers import Integral
from threading import Lock
from typing import Literal
from uuid import uuid4

import pandas as pd

from app.core.constants import COMMUNITY_GROUP_COLUMN_NAME
from app.models.enums import AnalysisModelKey, ColumnRole
from app.features.ingestion.cleaning_services import AnalysisReadyDatasetService
from app.features.results.metadata_filter import MetadataFilterDefinition, MetadataFilterService
from app.features.results.models import (
    AnalysisGroupDocumentsPage,
    AnalysisNgramDocumentsPage,
    DatasetName,
    ResultRowsPage,
    StoredAnalysisSnapshot,
    StoredDatasetSelection,
    StoredResultDatasets,
)
from app.features.results.paging import ResultStorePagingService
from app.features.results.snapshot import ResultStoreSnapshotService
from app.features.analysis.topic_analysis_services.contracts import AnalysisRunResult

logger = logging.getLogger(__name__)
ResultExportScope = Literal["clean_data", "verbatim_only"]
COMMUNITY_ID_COLUMN_NAME = "community_id"
COMMUNITY_LABEL_COLUMN_NAME = "community_label"


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
        self._analysis_snapshots: dict[str, StoredAnalysisSnapshot] = {}
        self._lock = Lock()
        self.snapshot_service = ResultStoreSnapshotService()
        self.paging_service = ResultStorePagingService()

    def save(
        self,
        transformed_df: pd.DataFrame,
        analysis_df: pd.DataFrame,
        *,
        metadata_columns: list[str],
        verbatim_columns: list[str],
    ) -> str:
        """Persist a transformed+analysis dataset pair and return the new result_id.

        Evicts the oldest entry (LRU) when the in-memory store exceeds max_results.
        """
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
            # OrderedDict with last=False pops the oldest (first-inserted) entry.
            while len(self._results) > self.max_results:
                evicted_result_id, _evicted = self._results.popitem(last=False)
                self._analysis_snapshots.pop(evicted_result_id, None)

        return result_id

    def delete(self, result_id: str) -> bool:
        with self._lock:
            removed = self._results.pop(result_id, None)
            self._analysis_snapshots.pop(result_id, None)
        return removed is not None

    def get_filters(self, result_id: str) -> list[MetadataFilterDefinition]:
        with self._lock:
            stored = self._results.get(result_id)

        if stored is None:
            raise ResultNotFoundError(f"No stored result exists for id '{result_id}'.")

        return list(stored.available_filters)

    def update_column_role(
        self,
        result_id: str,
        *,
        column_name: str,
        role: ColumnRole,
    ) -> StoredResultDatasets:
        """Reassign a column between metadata and verbatim roles, rebuild the analysis dataset, and invalidate any cached analysis snapshot."""
        with self._lock:
            stored = self._results.get(result_id)
            if stored is None:
                raise ResultNotFoundError(f"No stored result exists for id '{result_id}'.")

            if column_name not in stored.transformed_df.columns:
                raise ValueError(f"Column '{column_name}' is not present in the transformed dataset.")

            metadata_columns = [column for column in stored.metadata_columns if column != column_name]
            verbatim_columns = [column for column in stored.verbatim_columns if column != column_name]
            if role == ColumnRole.METADATA:
                metadata_columns.append(column_name)
            else:
                verbatim_columns.append(column_name)

            # Rebuild the analysis-ready frame from the transformed source of truth
            # so column-role edits never mutate the raw transformed dataset itself.
            analysis_df, resolved_metadata, resolved_verbatim = self.analysis_ready_service.build_from_assignments(
                stored.transformed_df,
                metadata_columns=metadata_columns,
                verbatim_columns=verbatim_columns,
            )
            available_filters = self.metadata_filter_service.build_definitions(
                stored.transformed_df,
                metadata_columns=resolved_metadata,
            )

            stored.analysis_df = analysis_df.copy()
            stored.metadata_columns = list(resolved_metadata)
            stored.verbatim_columns = list(resolved_verbatim)
            stored.available_filters = list(available_filters)
            self._analysis_snapshots.pop(result_id, None)
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

        if dataset == "community_analysis":
            return self._build_community_analysis_selection(
                result_id=result_id,
                stored=stored,
                filters=filters,
            )

        # Always filter a copy so callers can page/slice safely without sharing a
        # mutable DataFrame object across requests.
        unfiltered_df = (stored.transformed_df if dataset == "transformed" else stored.analysis_df).copy()
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

    def get_export_dataframe(
        self,
        result_id: str,
        *,
        scope: ResultExportScope,
        filters: dict[str, list[str]] | None = None,
    ) -> pd.DataFrame:
        with self._lock:
            stored = self._results.get(result_id)

        if stored is None:
            raise ResultNotFoundError(f"No stored result exists for id '{result_id}'.")

        filtered_df = self.metadata_filter_service.apply_filters(
            stored.transformed_df.copy(),
            filters=filters,
            allowed_columns={definition.column_name for definition in stored.available_filters},
        )
        if scope == "clean_data":
            return filtered_df.copy()

        if scope == "verbatim_only":
            verbatim_columns = [
                column_name
                for column_name in stored.verbatim_columns
                if column_name in filtered_df.columns
            ]
            if not verbatim_columns:
                raise ValueError("No verbatim columns are available to export.")
            return filtered_df[verbatim_columns].copy()

        raise ValueError(f"Unsupported export scope '{scope}'.")

    def save_analysis_snapshot(
        self,
        result_id: str,
        *,
        text_column_name: str,
        model_key: AnalysisModelKey,
        analysis_result: AnalysisRunResult,
    ) -> None:
        with self._lock:
            if result_id not in self._results:
                raise ResultNotFoundError(f"No stored result exists for id '{result_id}'.")
            if analysis_result.model_key != model_key:
                raise ValueError("The cached analysis result model key does not match the snapshot request.")
            snapshot = self.snapshot_service.build_snapshot(
                text_column_name=text_column_name,
                analysis_result=analysis_result,
                build_ngram_lookup_key=self._build_ngram_lookup_key,
            )
            if snapshot is None:
                self._analysis_snapshots.pop(result_id, None)
                return

            self._analysis_snapshots[result_id] = snapshot
            self._apply_group_mapping_column(
                self._results[result_id],
                analysis_result=analysis_result,
            )

    def get_fast_filtered_result(
        self,
        result_id: str,
        *,
        model_key: AnalysisModelKey,
        text_column_name: str,
        filters: dict[str, list[str]] | None,
    ) -> AnalysisRunResult | None:
        """Return a filtered analysis result from the cached snapshot without re-running ML.

        Returns None when the fast path is unavailable (no snapshot, or model/column mismatch).
        """
        with self._lock:
            snapshot = self._analysis_snapshots.get(result_id)
            stored = self._results.get(result_id)

        if snapshot is None or stored is None:
            return None
        if snapshot.model_key != model_key or snapshot.text_column_name != text_column_name:
            return None

        return self.snapshot_service.build_fast_filtered_result(
            result_id=result_id,
            snapshot=snapshot,
            stored=stored,
            metadata_filter_service=self.metadata_filter_service,
            filters=filters,
        )

    def get_analysis_group_page(
        self,
        result_id: str,
        *,
        group_id: str,
        offset: int,
        limit: int,
    ) -> AnalysisGroupDocumentsPage:
        if limit <= 0:
            raise ValueError("limit must be a positive integer.")

        with self._lock:
            snapshot = self._analysis_snapshots.get(result_id)

        if snapshot is None:
            raise ResultNotFoundError(f"No stored analysis snapshot exists for id '{result_id}'.")

        return self.paging_service.build_group_page(
            snapshot=snapshot,
            result_id=result_id,
            group_id=group_id,
            offset=offset,
            limit=limit,
            page_cls=AnalysisGroupDocumentsPage,
        )

    def get_analysis_ngram_page(
        self,
        result_id: str,
        *,
        ngram_size: int,
        term: str,
        offset: int,
        limit: int,
    ) -> AnalysisNgramDocumentsPage:
        if limit <= 0:
            raise ValueError("limit must be a positive integer.")

        with self._lock:
            snapshot = self._analysis_snapshots.get(result_id)

        if snapshot is None:
            raise ResultNotFoundError(f"No stored analysis snapshot exists for id '{result_id}'.")

        return self.paging_service.build_ngram_page(
            snapshot=snapshot,
            result_id=result_id,
            ngram_size=ngram_size,
            term=term,
            offset=offset,
            limit=limit,
            page_cls=AnalysisNgramDocumentsPage,
            build_ngram_lookup_key=self._build_ngram_lookup_key,
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

        selection = self.get_dataset(result_id, dataset=dataset, filters=filters)
        return self.paging_service.build_rows_page(
            stored=stored,
            selection=selection,
            result_id=result_id,
            dataset=dataset,
            offset=offset,
            limit=limit,
            page_cls=ResultRowsPage,
        )

    @staticmethod
    def _build_ngram_lookup_key(ngram_size: int, term: str) -> str:
        """Build a stable, case-insensitive lookup key combining n-gram size and term text."""
        return f"{int(ngram_size)}::{str(term).strip().casefold()}"

    @staticmethod
    def _apply_group_mapping_column(
        stored: StoredResultDatasets,
        *,
        analysis_result: AnalysisRunResult,
    ) -> None:
        if analysis_result.model_key != AnalysisModelKey.COMMUNITY:
            return

        row_to_group_label: dict[int, str] = {}
        for group in analysis_result.groups:
            label = str(group.label or f"Community {group.group_id}").strip()
            for document in group.documents:
                if int(document.row_number) > 0:
                    row_to_group_label[int(document.row_number)] = label

        for dataframe in (stored.transformed_df, stored.analysis_df):
            dataframe[COMMUNITY_GROUP_COLUMN_NAME] = ""
            for row_number, label in row_to_group_label.items():
                row_index = row_number - 1
                if row_index in dataframe.index:
                    dataframe.at[row_index, COMMUNITY_GROUP_COLUMN_NAME] = label

    def _build_community_analysis_selection(
        self,
        *,
        result_id: str,
        stored: StoredResultDatasets,
        filters: dict[str, list[str]] | None,
    ) -> StoredDatasetSelection:
        snapshot = self._analysis_snapshots.get(result_id)
        if snapshot is None or snapshot.model_key != AnalysisModelKey.COMMUNITY:
            raise ValueError("Community assignment data is only available after running community detection.")
        if snapshot.text_column_name not in stored.analysis_df.columns:
            raise ValueError("The analysed response column is no longer available in the analysis dataset.")

        filtered_df = self.metadata_filter_service.apply_filters(
            stored.analysis_df.copy(),
            filters=filters,
            allowed_columns={definition.column_name for definition in stored.available_filters},
        )
        filtered_row_numbers = {
            row_number
            for index in filtered_df.index
            if (row_number := self._resolve_dataframe_row_number(index)) > 0
        }
        identifier_column = self._resolve_identifier_column(
            stored.analysis_df,
            metadata_columns=stored.metadata_columns,
        )

        row_to_group: dict[int, tuple[str, str]] = {}
        for group in snapshot.groups.values():
            label = str(group.label or f"Community {group.group_id}").strip()
            for document in group.documents:
                row_number = int(document.row_number)
                if row_number > 0:
                    row_to_group[row_number] = (group.group_id, label)

        columns = []
        if identifier_column:
            columns.append(identifier_column)
        columns.extend([snapshot.text_column_name, COMMUNITY_LABEL_COLUMN_NAME, COMMUNITY_ID_COLUMN_NAME])

        records: list[dict[str, object | None]] = []
        for row_index, source_row in filtered_df.iterrows():
            row_number = self._resolve_dataframe_row_number(row_index)
            if row_number not in filtered_row_numbers or row_number not in row_to_group:
                continue

            group_id, group_label = row_to_group[row_number]
            record: dict[str, object | None] = {
                snapshot.text_column_name: self._serialize_cell(source_row.get(snapshot.text_column_name)),
                COMMUNITY_LABEL_COLUMN_NAME: group_label,
                COMMUNITY_ID_COLUMN_NAME: group_id,
            }
            if identifier_column:
                record[identifier_column] = self._serialize_cell(source_row.get(identifier_column))
            records.append(record)

        dataframe = pd.DataFrame(records, columns=columns)
        return StoredDatasetSelection(
            result_id=result_id,
            dataset="community_analysis",
            dataframe=dataframe,
            total_row_count=len(row_to_group),
            metadata_columns=list(stored.metadata_columns),
            verbatim_columns=list(stored.verbatim_columns),
        )

    @classmethod
    def _resolve_identifier_column(cls, dataframe: pd.DataFrame, *, metadata_columns: list[str]) -> str | None:
        candidate_columns = [
            column
            for column in metadata_columns
            if column in dataframe.columns
        ]
        candidate_columns.extend(
            column
            for column in dataframe.columns
            if column not in set(candidate_columns)
        )

        best_column: str | None = None
        best_score = 0
        for column in candidate_columns:
            score = cls._identifier_column_score(str(column))
            if score > best_score:
                best_column = str(column)
                best_score = score
        return best_column

    @staticmethod
    def _identifier_column_score(column_name: str) -> int:
        normalized = re.sub(r"__idx_\d+$", "", column_name.strip(), flags=re.IGNORECASE)
        normalized = re.sub(r"[_\W]+", " ", normalized.casefold()).strip()
        compact = normalized.replace(" ", "")
        tokens = set(normalized.split())

        if compact in {"responseid", "communityid", "communitylabel", "communitygroup"}:
            return 0
        if {"response", "id"} <= tokens or "community" in tokens:
            return 0

        if compact in {"userid", "respondentid", "submissionid", "participantid", "recordid", "customerid"}:
            return 100
        if "id" in tokens and tokens & {
            "contact",
            "customer",
            "participant",
            "record",
            "respondent",
            "submission",
            "user",
        }:
            return 95
        if "email" in tokens or compact in {"email", "emailaddress"}:
            return 85
        if normalized in {"name", "full name"} or "name" in tokens and tokens & {
            "contact",
            "customer",
            "participant",
            "person",
            "respondent",
            "school",
            "user",
        }:
            return 80
        if normalized == "id" or normalized.endswith(" id"):
            return 70
        return 0

    @staticmethod
    def _serialize_cell(value: object) -> object | None:
        if pd.isna(value):
            return None
        return value

    @staticmethod
    def _resolve_dataframe_row_number(row_index: object) -> int:
        if isinstance(row_index, Integral):
            return int(row_index) + 1
        if isinstance(row_index, float) and row_index.is_integer():
            return int(row_index) + 1
        return 0
