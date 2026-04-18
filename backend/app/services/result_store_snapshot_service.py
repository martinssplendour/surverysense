from __future__ import annotations

from collections import defaultdict

from app.core.constants import MODEL_LABELS


class ResultStoreSnapshotService:
    def build_snapshot(
        self,
        *,
        result_id: str,
        text_column_name: str,
        model_key: str,
        analysis_result: dict[str, object],
        group_snapshot_cls,
        ngram_snapshot_cls,
        snapshot_cls,
        build_ngram_lookup_key,
    ):
        groups_payload = analysis_result.get("groups", [])
        if not isinstance(groups_payload, list):
            return None

        groups = {}
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
            groups[group_id] = group_snapshot_cls(
                group_id=group_id,
                label=str(group.get("label", "Unlabelled group")).strip() or "Unlabelled group",
                count=int(group.get("count", len(documents)) or 0),
                documents=documents,
                meta=meta,
            )

        ngram_items_payload = analysis_result.get("ngram_buckets", [])
        ngram_items = {}
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
                    ngram_items[build_ngram_lookup_key(ngram_size, lookup_term)] = ngram_snapshot_cls(
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

        return snapshot_cls(
            text_column_name=text_column_name,
            model_key=model_key,
            groups=groups,
            ngram_items=ngram_items,
            scatter_points=scatter_points,
        )

    def build_fast_filtered_result(
        self,
        *,
        result_id: str,
        snapshot,
        stored,
        metadata_filter_service,
        filters: dict[str, list[str]] | None,
    ) -> dict[str, object]:
        filtered_df = metadata_filter_service.apply_filters(
            stored.analysis_df,
            filters=filters or {},
            allowed_columns={d.column_name for d in stored.available_filters},
        )
        filtered_row_numbers: frozenset[int] = frozenset(int(idx) + 1 for idx in filtered_df.index)

        surviving = {}
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

        filtered_scatter = [
            pt for pt in snapshot.scatter_points
            if pt["row_number"] in filtered_row_numbers
        ]

        buckets_by_size = defaultdict(list)
        for item in snapshot.ngram_items.values():
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
        ngram_size_labels = {1: "Single Words", 2: "Two-Word Phrases", 3: "Three-Word Phrases"}
        ngram_buckets = [
            {
                "label": ngram_size_labels.get(size, f"{size}-Word Phrases"),
                "ngram_size": size,
                "items": sorted(items, key=lambda x: -int(x["count"])),
            }
            for size, items in sorted(buckets_by_size.items())
        ]

        return {
            "ok": True,
            "result_id": result_id,
            "model_key": snapshot.model_key,
            "model_label": MODEL_LABELS.get(snapshot.model_key, snapshot.model_key.upper()),
            "text_column_name": snapshot.text_column_name,
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
