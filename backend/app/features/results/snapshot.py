from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable

import pandas as pd

from app.core.constants import MODEL_LABELS
from app.features.analysis.topic_analysis_services.contracts import (
    AnalysisGroupRecord,
    AnalysisNgramBucketRecord,
    AnalysisNgramItemRecord,
    AnalysisRunResult,
)
from app.features.common.document_relevance import DocumentRelevanceSorter
from app.features.results.models import (
    StoredAnalysisGroupSnapshot,
    StoredAnalysisNgramSnapshot,
    StoredAnalysisSnapshot,
    StoredResultDatasets,
)


class ResultStoreSnapshotService:
    PLACEHOLDER_VALUES = frozenset({"", "na", "n/a", "nan", "none", "null", "nil", "-", "--"})

    def build_snapshot(
        self,
        *,
        text_column_name: str,
        analysis_result: AnalysisRunResult,
        build_ngram_lookup_key: Callable[[int, str], str],
    ) -> StoredAnalysisSnapshot | None:
        if not analysis_result.groups and not analysis_result.ngram_buckets:
            return None

        groups = {
            group.group_id: StoredAnalysisGroupSnapshot(
                group_id=group.group_id,
                label=group.label or "Unlabelled group",
                count=int(group.count or len(group.documents)),
                documents=list(group.documents),
                source_label=group.source_label,
                translated=bool(group.translated),
                ai_generated=bool(group.ai_generated),
                terms=list(group.terms),
                term_strengths=dict(group.term_strengths),
                examples=list(group.examples),
                is_noise=bool(group.is_noise),
            )
            for group in analysis_result.groups
            if group.group_id.strip()
        }

        ngram_items: dict[str, StoredAnalysisNgramSnapshot] = {}
        for bucket in analysis_result.ngram_buckets:
            if int(bucket.ngram_size) <= 0:
                continue
            for item in bucket.items:
                lookup_term = (item.source_term or item.term).strip()
                if not item.term.strip() or not lookup_term:
                    continue
                ngram_items[build_ngram_lookup_key(bucket.ngram_size, lookup_term)] = StoredAnalysisNgramSnapshot(
                    term=item.term,
                    source_term=item.source_term,
                    ngram_size=int(bucket.ngram_size),
                    hit_count=int(item.count or len(item.documents)),
                    translated=bool(item.translated),
                    document_count=int(item.document_count or len(item.documents)),
                    documents=list(item.documents),
                )

        return StoredAnalysisSnapshot(
            text_column_name=text_column_name,
            model_key=analysis_result.model_key,
            community_similarity_threshold=analysis_result.community_similarity_threshold,
            original_response_count=int(analysis_result.original_response_count or 0),
            groups=groups,
            ngram_items=ngram_items,
            scatter_points=list(analysis_result.scatter_points),
            network_edges=list(analysis_result.network_edges),
        )

    def build_fast_filtered_result(
        self,
        *,
        result_id: str,
        snapshot: StoredAnalysisSnapshot,
        stored: StoredResultDatasets,
        metadata_filter_service,
        filters: dict[str, list[str]] | None,
    ) -> AnalysisRunResult:
        filtered_df = metadata_filter_service.apply_filters(
            stored.analysis_df,
            filters=filters or {},
            allowed_columns={definition.column_name for definition in stored.available_filters},
        )
        filtered_row_numbers: frozenset[int] = frozenset(int(idx) + 1 for idx in filtered_df.index)
        original_response_count = self._count_original_responses(
            filtered_df,
            text_column_name=snapshot.text_column_name,
        )

        rebuilt_groups: list[AnalysisGroupRecord] = []
        surviving_total = 0
        for group in snapshot.groups.values():
            documents = [
                document
                for document in group.documents
                if document.row_number in filtered_row_numbers
            ]
            if not documents:
                continue
            surviving_total += len(documents)
            rebuilt_groups.append(
                AnalysisGroupRecord(
                    group_id=group.group_id,
                    label=group.label,
                    source_label=group.source_label,
                    translated=group.translated,
                    ai_generated=group.ai_generated,
                    count=len(documents),
                    share=0.0,
                    total_documents=0,
                    terms=list(group.terms),
                    term_strengths=dict(group.term_strengths),
                    examples=list(group.examples),
                    is_noise=group.is_noise,
                    documents=documents,
                )
            )

        total_denom = max(1, surviving_total)
        for group in rebuilt_groups:
            group.documents = DocumentRelevanceSorter.order_by_label_and_terms(
                group.documents,
                label=group.label,
                terms=group.terms,
            )
            group.examples = DocumentRelevanceSorter.order_by_label_and_terms(
                group.examples,
                label=group.label,
                terms=group.terms,
            )
            group.share = round(len(group.documents) / total_denom, 4)
            group.total_documents = total_denom
            group.comment = (
                f"{group.label} appears in {len(group.documents)} response(s), "
                f"representing {round(group.share * 100)}% of the filtered sample."
            )
            group.count = len(group.documents)
        rebuilt_groups.sort(key=lambda group: (-int(group.count), group.group_id))

        filtered_scatter = [
            point
            for point in snapshot.scatter_points
            if point.row_number in filtered_row_numbers
        ]
        filtered_network_edges = [
            edge
            for edge in snapshot.network_edges
            if edge.source_row_number in filtered_row_numbers and edge.target_row_number in filtered_row_numbers
        ]

        buckets_by_size: dict[int, list[AnalysisNgramItemRecord]] = defaultdict(list)
        for item in snapshot.ngram_items.values():
            filtered_documents = [
                document
                for document in item.documents
                if document.row_number in filtered_row_numbers
            ]
            filtered_count = len(filtered_documents)
            if filtered_count == 0:
                continue
            buckets_by_size[item.ngram_size].append(
                AnalysisNgramItemRecord(
                    term=item.term,
                    source_term=item.source_term,
                    translated=item.translated,
                    count=filtered_count,
                    document_count=filtered_count,
                    documents=list(filtered_documents),
                )
            )

        ngram_size_labels = {1: "Single Words", 2: "Two-Word Phrases", 3: "Three-Word Phrases"}
        rebuilt_buckets: list[AnalysisNgramBucketRecord] = []
        for size, items in sorted(buckets_by_size.items()):
            rebuilt_buckets.append(
                AnalysisNgramBucketRecord(
                    label=ngram_size_labels.get(size, f"{size}-Word Phrases"),
                    ngram_size=size,
                    items=sorted(items, key=lambda item: -int(item.count)),
                )
            )

        return AnalysisRunResult(
            ok=True,
            result_id=result_id,
            model_key=snapshot.model_key,
            model_label=MODEL_LABELS[snapshot.model_key],
            text_column_name=snapshot.text_column_name,
            filtered_row_count=int(len(filtered_df)),
            valid_document_count=surviving_total,
            original_response_count=original_response_count,
            skipped_document_count=max(0, int(len(filtered_df)) - original_response_count),
            translated_document_count=0,
            community_similarity_threshold=snapshot.community_similarity_threshold,
            warnings=[],
            error=None,
            groups=rebuilt_groups,
            ngram_buckets=rebuilt_buckets,
            scatter_points=filtered_scatter,
            network_edges=filtered_network_edges,
        )

    @classmethod
    def _count_original_responses(cls, dataframe: pd.DataFrame, *, text_column_name: str) -> int:
        if text_column_name not in dataframe.columns:
            return 0

        count = 0
        for _row_index, raw_value in dataframe[text_column_name].items():
            if pd.isna(raw_value):
                continue
            normalized = str(raw_value).strip()
            if normalized.casefold() in cls.PLACEHOLDER_VALUES:
                continue
            count += 1
        return count
