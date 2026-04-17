"""In-memory store for transformed datasets, analysis snapshots, and paged document retrieval."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import logging
from threading import Lock
from typing import Literal
from uuid import uuid4

import pandas as pd

from app.core.constants import MODEL_LABELS
from app.models.enums import ColumnRole
from app.services.cleaning_services import AnalysisReadyDatasetService
from app.services.metadata_filter_service import MetadataFilterDefinition, MetadataFilterService


DatasetName = Literal["transformed", "analysis"]
logger = logging.getLogger(__name__)


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

    def save_analysis_snapshot(
        self,
        result_id: str,
        *,
        text_column_name: str,
        model_key: str,
        analysis_result: dict[str, object],
    ) -> None:
        with self._lock:
            if result_id not in self._results:
                raise ResultNotFoundError(f"No stored result exists for id '{result_id}'.")

            # Cache only the lightweight pieces needed to rebuild filtered views and
            # drilldown modals; the expensive ML step should not rerun on every filter.
            groups_payload = analysis_result.get("groups", [])
            if not isinstance(groups_payload, list):
                self._analysis_snapshots.pop(result_id, None)
                return

            groups: dict[str, StoredAnalysisGroupSnapshot] = {}
            for group in groups_payload:
                if not isinstance(group, dict):
                    continue
                group_id = str(group.get("group_id", "")).strip()
                if not group_id:
                    continue
                documents_payload = group.get("_documents", [])
                documents: list[dict[str, object]] = []
                if isinstance(documents_payload, list):
                    for document in documents_payload:
                        if not isinstance(document, dict):
                            continue
                        row_number = int(document.get("row_number", 0) or 0)
                        text = str(document.get("text", "")).strip()
                        if row_number <= 0 or not text:
                            continue
                        documents.append(
                            {
                                "row_number": row_number,
                                "text": text,
                            }
                        )
                meta = {
                    "source_label": group.get("source_label"),
                    "translated": bool(group.get("translated", False)),
                    "ai_generated": bool(group.get("ai_generated", False)),
                    "terms": list(group.get("terms", [])),
                    "examples": list(group.get("examples", [])),
                    "is_noise": bool(group.get("is_noise", False)),
                }
                groups[group_id] = StoredAnalysisGroupSnapshot(
                    group_id=group_id,
                    label=str(group.get("label", "Unlabelled group")).strip() or "Unlabelled group",
                    count=int(group.get("count", len(documents)) or 0),
                    documents=documents,
                    meta=meta,
                )

            ngram_items_payload = analysis_result.get("ngram_buckets", [])
            ngram_items: dict[str, StoredAnalysisNgramSnapshot] = {}
            if isinstance(ngram_items_payload, list):
                for bucket in ngram_items_payload:
                    if not isinstance(bucket, dict):
                        continue
                    ngram_size = int(bucket.get("ngram_size", 0) or 0)
                    if ngram_size <= 0:
                        continue
                    items_payload = bucket.get("items", [])
                    if not isinstance(items_payload, list):
                        continue
                    for item in items_payload:
                        if not isinstance(item, dict):
                            continue
                        term = str(item.get("term", "")).strip()
                        raw_source_term = item.get("source_term")
                        source_term = str(raw_source_term).strip() if isinstance(raw_source_term, str) else None
                        lookup_term = source_term or term
                        if not term or not lookup_term:
                            continue
                        documents_payload = item.get("_documents", [])
                        documents: list[dict[str, object]] = []
                        if isinstance(documents_payload, list):
                            for document in documents_payload:
                                if not isinstance(document, dict):
                                    continue
                                row_number = int(document.get("row_number", 0) or 0)
                                text = str(document.get("text", "")).strip()
                                if row_number <= 0 or not text:
                                    continue
                                documents.append(
                                    {
                                        "row_number": row_number,
                                        "text": text,
                                    }
                                )
                        ngram_items[self._build_ngram_lookup_key(ngram_size, lookup_term)] = StoredAnalysisNgramSnapshot(
                            term=term,
                            source_term=source_term,
                            ngram_size=ngram_size,
                            hit_count=int(item.get("count", len(documents)) or 0),
                            documents=documents,
                        )

            scatter_points_payload = analysis_result.get("scatter_points", [])
            scatter_points: list[dict[str, object]] = []
            if isinstance(scatter_points_payload, list):
                for point in scatter_points_payload:
                    if not isinstance(point, dict):
                        continue
                    row_number = int(point.get("row_number", 0) or 0)
                    if row_number <= 0:
                        continue
                    scatter_points.append(
                        {
                            "row_number": row_number,
                            "text": str(point.get("text", "")),
                            "group_id": str(point.get("group_id", "")),
                            "group_label": str(point.get("group_label", "")),
                            "x": float(point.get("x", 0.0)),
                            "y": float(point.get("y", 0.0)),
                        }
                    )

            self._analysis_snapshots[result_id] = StoredAnalysisSnapshot(
                text_column_name=text_column_name,
                model_key=model_key,
                groups=groups,
                ngram_items=ngram_items,
                scatter_points=scatter_points,
            )

    def get_fast_filtered_result(
        self,
        result_id: str,
        *,
        model_key: str,
        text_column_name: str,
        filters: dict[str, list[str]] | None,
    ) -> dict[str, object] | None:
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

        # Snapshot documents store 1-based row numbers, so convert the filtered
        # DataFrame index back into that same numbering before intersecting.
        filtered_df = self.metadata_filter_service.apply_filters(
            stored.analysis_df,
            filters=filters or {},
            allowed_columns={d.column_name for d in stored.available_filters},
        )
        # DataFrame index is 0-based; row_number in documents uses 1-based numbering.
        filtered_row_numbers: frozenset[int] = frozenset(int(idx) + 1 for idx in filtered_df.index)

        surviving: dict[str, list[dict[str, object]]] = {}
        for group in snapshot.groups.values():
            surviving[group.group_id] = [
                doc for doc in group.documents
                if doc["row_number"] in filtered_row_numbers
            ]
        total_surviving = sum(len(docs) for docs in surviving.values())
        total_denom = max(1, total_surviving)

        rebuilt_groups: list[dict[str, object]] = []
        for group in snapshot.groups.values():
            docs = surviving[group.group_id]
            count = len(docs)
            if count == 0:
                continue
            # Shares are recomputed against the filtered surviving set, not the
            # original analysis total, so the UI percentages stay truthful.
            share = round(count / total_denom, 4)
            share_pct = round(share * 100)
            comment = (
                f"{group.label} appears in {count} response(s), "
                f"representing {share_pct}% of the filtered sample."
            )
            rebuilt_groups.append(
                {
                    "group_id": group.group_id,
                    "label": group.label,
                    **group.meta,
                    "count": count,
                    "share": share,
                    "total_documents": total_denom,
                    "comment": comment,
                }
            )
        rebuilt_groups.sort(key=lambda g: (-int(g["count"]), str(g["group_id"])))

        filtered_scatter: list[dict[str, object]] = [
            pt for pt in snapshot.scatter_points
            if pt["row_number"] in filtered_row_numbers
        ]

        from collections import defaultdict as _defaultdict
        buckets_by_size: dict[int, list[dict[str, object]]] = _defaultdict(list)
        for item in snapshot.ngram_items.values():
            # Fast-path n-gram rebuild is intentionally approximate: it counts
            # matching documents, not repeated occurrences within one document.
            filtered_docs = [d for d in item.documents if d["row_number"] in filtered_row_numbers]
            filtered_count = len(filtered_docs)
            if filtered_count == 0:
                continue
            buckets_by_size[item.ngram_size].append(
                {
                    "term": item.term,
                    "source_term": item.source_term,
                    "count": filtered_count,
                    "document_count": filtered_count,
                }
            )
        _ngram_size_labels = {1: "Single Words", 2: "Two-Word Phrases", 3: "Three-Word Phrases"}
        ngram_buckets: list[dict[str, object]] = [
            {
                "label": _ngram_size_labels.get(size, f"{size}-Word Phrases"),
                "ngram_size": size,
                "items": sorted(items, key=lambda x: -int(x["count"])),
            }
            for size, items in sorted(buckets_by_size.items())
        ]

        return {
            "ok": True,
            "result_id": result_id,
            "model_key": model_key,
            "model_label": MODEL_LABELS.get(model_key, model_key.upper()),
            "text_column_name": text_column_name,
            "filtered_row_count": int(len(filtered_df)),
            "valid_document_count": total_surviving,
            "skipped_document_count": int(len(filtered_df)) - total_surviving,
            "translated_document_count": 0,
            "warnings": [],
            "error": None,
            "groups": rebuilt_groups,
            "ngram_buckets": ngram_buckets,
            "scatter_points": filtered_scatter,
        }

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

        normalized_group_id = str(group_id).strip()
        group = snapshot.groups.get(normalized_group_id)
        if group is None:
            raise ValueError(f"Analysis group '{normalized_group_id}' is not available.")

        normalized_offset = max(0, offset)
        documents = group.documents[normalized_offset: normalized_offset + limit]
        return AnalysisGroupDocumentsPage(
            result_id=result_id,
            group_id=group.group_id,
            group_label=group.label,
            text_column_name=snapshot.text_column_name,
            total_count=int(group.count),
            offset=normalized_offset,
            limit=limit,
            has_more=(normalized_offset + len(documents)) < len(group.documents),
            documents=[dict(document) for document in documents],
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

        normalized_term = str(term).strip()
        if not normalized_term:
            raise ValueError("term must not be empty.")

        item = snapshot.ngram_items.get(self._build_ngram_lookup_key(ngram_size, normalized_term))
        if item is None:
            raise ValueError(f"N-gram '{normalized_term}' is not available.")

        normalized_offset = max(0, offset)
        documents = item.documents[normalized_offset: normalized_offset + limit]
        return AnalysisNgramDocumentsPage(
            result_id=result_id,
            term=item.term,
            source_term=item.source_term,
            ngram_size=item.ngram_size,
            text_column_name=snapshot.text_column_name,
            total_count=len(item.documents),
            hit_count=int(item.hit_count),
            offset=normalized_offset,
            limit=limit,
            has_more=(normalized_offset + len(documents)) < len(item.documents),
            documents=[dict(document) for document in documents],
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
        # Replace NaN with None before JSON serialisation so the frontend does not
        # have to special-case pandas missing-value markers.
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

    @staticmethod
    def _build_ngram_lookup_key(ngram_size: int, term: str) -> str:
        """Build a stable, case-insensitive lookup key combining n-gram size and term text."""
        return f"{int(ngram_size)}::{str(term).strip().casefold()}"
