from __future__ import annotations

from app.core.constants import COMMUNITY_GROUP_COLUMN_NAME
from app.features.analysis.topic_analysis_services.contracts import AnalysisRunResult
from app.features.results.models import StoredResultDatasets
from app.models.enums import AnalysisModelKey


def apply_group_mapping_column(
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
