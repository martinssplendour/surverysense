from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from app.features.results.models import (
    AnalysisGroupDocumentsPage,
    AnalysisNgramDocumentsPage,
    DatasetName,
    ResultRowsPage,
    StoredAnalysisSnapshot,
    StoredDatasetSelection,
    StoredResultDatasets,
)


class ResultStorePagingService:
    def build_group_page(
        self,
        *,
        snapshot: StoredAnalysisSnapshot,
        result_id: str,
        group_id: str,
        offset: int,
        limit: int,
        page_cls: type[AnalysisGroupDocumentsPage],
    ) -> AnalysisGroupDocumentsPage:
        normalized_group_id = str(group_id).strip()
        group = snapshot.groups.get(normalized_group_id)
        if group is None:
            raise ValueError(f"Analysis group '{normalized_group_id}' is not available.")

        normalized_offset = max(0, offset)
        documents = group.documents[normalized_offset: normalized_offset + limit]
        return page_cls(
            result_id=result_id,
            group_id=group.group_id,
            group_label=group.label,
            text_column_name=snapshot.text_column_name,
            total_count=int(group.count),
            offset=normalized_offset,
            limit=limit,
            has_more=(normalized_offset + len(documents)) < len(group.documents),
            documents=list(documents),
        )

    def build_ngram_page(
        self,
        *,
        snapshot: StoredAnalysisSnapshot,
        result_id: str,
        ngram_size: int,
        term: str,
        offset: int,
        limit: int,
        page_cls: type[AnalysisNgramDocumentsPage],
        build_ngram_lookup_key: Callable[[int, str], str],
    ) -> AnalysisNgramDocumentsPage:
        normalized_term = str(term).strip()
        if not normalized_term:
            raise ValueError("term must not be empty.")

        item = snapshot.ngram_items.get(build_ngram_lookup_key(ngram_size, normalized_term))
        if item is None:
            raise ValueError(f"N-gram '{normalized_term}' is not available.")

        normalized_offset = max(0, offset)
        documents = item.documents[normalized_offset: normalized_offset + limit]
        return page_cls(
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
            documents=list(documents),
        )

    def build_rows_page(
        self,
        *,
        stored: StoredResultDatasets,
        selection: StoredDatasetSelection,
        result_id: str,
        dataset: DatasetName,
        offset: int,
        limit: int,
        page_cls: type[ResultRowsPage],
    ) -> ResultRowsPage:
        if dataset == "transformed":
            unfiltered_row_count = int(len(stored.transformed_df))
        elif dataset == "analysis":
            unfiltered_row_count = int(len(stored.analysis_df))
        else:
            unfiltered_row_count = int(selection.total_row_count)
        dataframe = selection.dataframe
        total_row_count = int(len(dataframe))
        normalized_offset = max(0, offset)
        page_df = dataframe.iloc[normalized_offset: normalized_offset + limit].copy()
        page_df = page_df.where(pd.notna(page_df), None)
        rows = page_df.to_dict(orient="records")

        return page_cls(
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
