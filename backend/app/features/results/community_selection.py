"""Community-assignment dataset construction for stored analysis results."""
from __future__ import annotations

import re
from numbers import Integral

import pandas as pd

from app.features.results.metadata_filter import MetadataFilterDefinition, MetadataFilterService
from app.features.results.models import StoredAnalysisSnapshot, StoredDatasetSelection, StoredResultDatasets

COMMUNITY_ID_COLUMN_NAME = "community_id"
COMMUNITY_LABEL_COLUMN_NAME = "community_label"


def build_community_analysis_selection(
    *,
    result_id: str,
    stored: StoredResultDatasets,
    snapshot: StoredAnalysisSnapshot,
    metadata_filter_service: MetadataFilterService,
    filters: dict[str, list[str]] | None,
) -> StoredDatasetSelection:
    """Build a paged-data source with response text and assigned community labels."""
    filtered_df = metadata_filter_service.apply_filters(
        stored.analysis_df.copy(),
        filters=filters,
        allowed_columns={definition.column_name for definition in stored.available_filters},
    )
    filtered_row_numbers = {
        row_number
        for index in filtered_df.index
        if (row_number := resolve_dataframe_row_number(index)) > 0
    }
    identifier_column = resolve_identifier_column(
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
        row_number = resolve_dataframe_row_number(row_index)
        if row_number not in filtered_row_numbers or row_number not in row_to_group:
            continue

        group_id, group_label = row_to_group[row_number]
        record: dict[str, object | None] = {
            snapshot.text_column_name: serialize_cell(source_row.get(snapshot.text_column_name)),
            COMMUNITY_LABEL_COLUMN_NAME: group_label,
            COMMUNITY_ID_COLUMN_NAME: group_id,
        }
        if identifier_column:
            record[identifier_column] = serialize_cell(source_row.get(identifier_column))
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


def resolve_identifier_column(dataframe: pd.DataFrame, *, metadata_columns: list[str]) -> str | None:
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
        score = identifier_column_score(str(column))
        if score > best_score:
            best_column = str(column)
            best_score = score
    return best_column


def identifier_column_score(column_name: str) -> int:
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


def serialize_cell(value: object) -> object | None:
    if pd.isna(value):
        return None
    return value


def resolve_dataframe_row_number(row_index: object) -> int:
    if isinstance(row_index, Integral):
        return int(row_index) + 1
    if isinstance(row_index, float) and row_index.is_integer():
        return int(row_index) + 1
    return 0
