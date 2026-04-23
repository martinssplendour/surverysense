from __future__ import annotations

import pandas as pd

from app.core.exceptions import RowLimitExceededError
from app.features.ingestion.cleaning_services import (
    DuplicateAnswerResolutionService,
    MetadataConsolidationService,
    MultipartVerbatimConsolidationService,
    NullScrubbingService,
    QuestionHeaderResolutionService,
    TextNormalizationService,
    VerbatimHeaderCleaningService,
    VerbatimRowFilterService,
    VerticalRecordAssemblyService,
    VerticalRecordFilterService,
)
from app.features.ingestion.vertical_transformation_service import VerticalTransformationService
from app.features.ingestion.wide_transformation_service import WideTransformationService
from app.models.manifest import LayoutState, TransformationManifest


class DataTransformationService:
    """
    Applies the manifest deterministically by integer indices.

    For vertical layouts the service does not jump straight into a raw pivot. It assembles
    normalized respondent/question/answer records first, removes duplicates, consolidates
    metadata by the respondent key, and only then creates the one-row-per-record output.
    """

    def __init__(
        self,
        text_normalizer: TextNormalizationService,
        null_scrubber: NullScrubbingService,
        question_header_resolver: QuestionHeaderResolutionService,
        verbatim_header_cleaner: VerbatimHeaderCleaningService,
        multipart_verbatim_consolidator: MultipartVerbatimConsolidationService,
        vertical_record_filter: VerticalRecordFilterService,
        duplicate_answer_resolver: DuplicateAnswerResolutionService,
        metadata_consolidator: MetadataConsolidationService,
        vertical_record_assembler: VerticalRecordAssemblyService,
        row_filter: VerbatimRowFilterService,
    ) -> None:
        self.text_normalizer = text_normalizer
        self.null_scrubber = null_scrubber
        self.question_header_resolver = question_header_resolver
        self.verbatim_header_cleaner = verbatim_header_cleaner
        self.multipart_verbatim_consolidator = multipart_verbatim_consolidator
        self.vertical_record_filter = vertical_record_filter
        self.duplicate_answer_resolver = duplicate_answer_resolver
        self.metadata_consolidator = metadata_consolidator
        self.vertical_record_assembler = vertical_record_assembler
        self.row_filter = row_filter
        self.wide_transformation_service = WideTransformationService()
        self.vertical_transformation_service = VerticalTransformationService(
            question_header_resolver=question_header_resolver,
            vertical_record_filter=vertical_record_filter,
            duplicate_answer_resolver=duplicate_answer_resolver,
            metadata_consolidator=metadata_consolidator,
            vertical_record_assembler=vertical_record_assembler,
        )

    def transform(self, raw_df: pd.DataFrame, manifest: TransformationManifest) -> pd.DataFrame:
        original_columns = raw_df.columns
        working_df, scoped_indices, index_map = self._scope_input_dataframe(raw_df, manifest)
        working_df = self.text_normalizer.clean_dataframe(working_df)
        working_df = self.null_scrubber.scrub_dataframe(working_df, manifest.null_equivalents)

        if manifest.layout_state == LayoutState.VERTICAL:
            transformed_df = self.vertical_transformation_service.build(
                working_df,
                manifest,
                original_columns=original_columns,
                scoped_indices=scoped_indices,
                index_map=index_map,
                metadata_output_columns=self._metadata_output_columns(manifest, original_columns),
                make_output_column_name=self._make_output_column_name,
            )
        else:
            transformed_df = self.wide_transformation_service.build(
                working_df,
                manifest,
                original_columns=original_columns,
                index_map=index_map,
                make_output_column_name=self._make_output_column_name,
            )
        metadata_columns = self._metadata_output_columns(manifest, original_columns)

        transformed_df = self.text_normalizer.clean_dataframe(transformed_df)
        transformed_df = self.null_scrubber.scrub_dataframe(transformed_df, manifest.null_equivalents)
        transformed_df = self.multipart_verbatim_consolidator.consolidate(
            transformed_df,
            metadata_columns=metadata_columns,
        )
        transformed_df = self.verbatim_header_cleaner.clean_and_sort(
            transformed_df,
            metadata_columns=metadata_columns,
        )
        verbatim_columns = [
            column for column in transformed_df.columns
            if column not in metadata_columns
        ]
        transformed_df = self.row_filter.drop_empty_rows(transformed_df, verbatim_columns)

        if len(transformed_df) > manifest.row_limit:
            raise RowLimitExceededError(
                f"Transformed dataframe has {len(transformed_df)} rows which exceeds the safety limit of {manifest.row_limit}."
            )
        return transformed_df.reset_index(drop=True)

    def _metadata_output_columns(
        self,
        manifest: TransformationManifest,
        original_columns: pd.Index,
    ) -> list[str]:
        if manifest.layout_state == LayoutState.WIDE:
            ordered_indices = manifest.metadata_indices
            return [
                self._make_output_column_name(original_columns[idx], idx)
                for idx in ordered_indices
            ]

        ordered_indices = list(dict.fromkeys(
            manifest.vertical_assembly.record_key_indices + manifest.metadata_indices
        ))
        return [
            self._make_output_column_name(original_columns[idx], idx)
            for idx in ordered_indices
        ]

    def _scope_input_dataframe(
        self,
        raw_df: pd.DataFrame,
        manifest: TransformationManifest,
    ) -> tuple[pd.DataFrame, list[int], dict[int, int]]:
        scoped_indices = self._required_input_indices(manifest)
        scoped_df = raw_df.iloc[:, scoped_indices].copy() if scoped_indices else raw_df.iloc[:, :0].copy()
        index_map = {
            original_idx: scoped_idx
            for scoped_idx, original_idx in enumerate(scoped_indices)
        }
        return scoped_df, scoped_indices, index_map

    @staticmethod
    def _required_input_indices(manifest: TransformationManifest) -> list[int]:
        if manifest.layout_state == LayoutState.WIDE:
            required = manifest.metadata_indices + manifest.verbatim_indices
            return sorted(set(required))

        vertical_plan = manifest.vertical_assembly
        required = (
            vertical_plan.record_key_indices
            + vertical_plan.question_header_indices
            + vertical_plan.helper_indices
            + manifest.metadata_indices
        )
        if vertical_plan.resolved_answer_col_idx is not None:
            required.append(vertical_plan.resolved_answer_col_idx)
        return sorted(set(required))

    @staticmethod
    def _make_output_column_name(column_name: object, column_idx: int) -> str:
        normalized = str(column_name).strip() if str(column_name).strip() else f"column_{column_idx}"
        return f"{normalized}__idx_{column_idx}"
