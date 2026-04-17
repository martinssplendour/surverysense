from __future__ import annotations

import pandas as pd

from app.services.cleaning_services.metadata_selection_service import MetadataColumnSelectionService
from app.services.cleaning_services.multipart_service import MultipartVerbatimConsolidationService
from app.services.cleaning_services.row_filter_service import VerbatimRowFilterService
from app.services.cleaning_services.verbatim_selection_service import VerbatimQuestionSelectionService


class AnalysisReadyDatasetService:
    """Builds the final analysis-ready slice from a transformed dataframe."""

    def __init__(
        self,
        metadata_selector: MetadataColumnSelectionService,
        verbatim_selector: VerbatimQuestionSelectionService,
        multipart_verbatim_consolidator: MultipartVerbatimConsolidationService,
        row_filter: VerbatimRowFilterService,
    ) -> None:
        self.metadata_selector = metadata_selector
        self.verbatim_selector = verbatim_selector
        self.multipart_verbatim_consolidator = multipart_verbatim_consolidator
        self.row_filter = row_filter

    def build(self, df: pd.DataFrame) -> tuple[pd.DataFrame, list[str], list[str]]:
        if df.empty:
            metadata_columns = self.metadata_selector.select_columns(df)
            return df.copy(), metadata_columns, []

        metadata_columns = self.metadata_selector.select_columns(df)
        working_df = self.multipart_verbatim_consolidator.consolidate(
            df,
            metadata_columns=metadata_columns,
        )
        verbatim_columns = self.verbatim_selector.select_columns(
            working_df,
            metadata_columns=metadata_columns,
        )
        selected_columns = metadata_columns + [
            column for column in verbatim_columns
            if column not in set(metadata_columns)
        ]
        return working_df[selected_columns].copy(), metadata_columns, verbatim_columns

    def build_from_assignments(
        self,
        df: pd.DataFrame,
        *,
        metadata_columns: list[str],
        verbatim_columns: list[str],
    ) -> tuple[pd.DataFrame, list[str], list[str]]:
        if df.empty:
            resolved_metadata = [column for column in metadata_columns if column in df.columns]
            resolved_verbatim = [column for column in verbatim_columns if column in df.columns and column not in set(resolved_metadata)]
            selected_columns = resolved_metadata + resolved_verbatim
            return df[selected_columns].copy(), resolved_metadata, resolved_verbatim

        resolved_metadata = []
        seen_columns: set[str] = set()
        for column in metadata_columns:
            if column in df.columns and column not in seen_columns:
                resolved_metadata.append(column)
                seen_columns.add(column)

        resolved_verbatim = []
        for column in verbatim_columns:
            if column in df.columns and column not in seen_columns:
                resolved_verbatim.append(column)
                seen_columns.add(column)

        selected_columns = resolved_metadata + resolved_verbatim
        analysis_df = df[selected_columns].copy()
        analysis_df = self.row_filter.drop_empty_rows(analysis_df, resolved_verbatim)
        return analysis_df, resolved_metadata, resolved_verbatim
