from __future__ import annotations

import pandas as pd

from app.core.exceptions import ManifestBuildError, RowLimitExceededError
from app.models.manifest import LayoutState, TransformationManifest
from app.services.cleaning_services import (
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

    def transform(self, raw_df: pd.DataFrame, manifest: TransformationManifest) -> pd.DataFrame:
        original_columns = raw_df.columns
        working_df, scoped_indices, index_map = self._scope_input_dataframe(raw_df, manifest)
        working_df = self.text_normalizer.clean_dataframe(working_df)
        working_df = self.null_scrubber.scrub_dataframe(working_df, manifest.null_equivalents)

        if manifest.layout_state == LayoutState.VERTICAL:
            transformed_df = self._transform_vertical(
                working_df,
                manifest,
                original_columns=original_columns,
                scoped_indices=scoped_indices,
                index_map=index_map,
            )
        else:
            transformed_df = self._transform_wide(
                working_df,
                manifest,
                original_columns=original_columns,
                index_map=index_map,
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

    def _transform_wide(
        self,
        raw_df: pd.DataFrame,
        manifest: TransformationManifest,
        *,
        original_columns: pd.Index,
        index_map: dict[int, int],
    ) -> pd.DataFrame:
        keep_indices = manifest.metadata_indices + [
            idx for idx in manifest.verbatim_indices if idx not in set(manifest.metadata_indices)
        ]
        if not keep_indices:
            raise ManifestBuildError("Wide manifest did not provide any columns to keep.")

        selected_columns = {
            self._make_output_column_name(original_columns[idx], idx): raw_df.iloc[:, index_map[idx]]
            for idx in keep_indices
        }
        return pd.DataFrame(selected_columns)

    def _transform_vertical(
        self,
        raw_df: pd.DataFrame,
        manifest: TransformationManifest,
        *,
        original_columns: pd.Index,
        scoped_indices: list[int],
        index_map: dict[int, int],
    ) -> pd.DataFrame:
        vertical_plan = manifest.vertical_assembly
        answer_idx = vertical_plan.resolved_answer_col_idx
        if answer_idx is None:
            raise ManifestBuildError("Vertical manifest is missing answer_col_idx.")
        if not vertical_plan.record_key_indices:
            raise ManifestBuildError("Vertical manifest is missing record_key_indices.")
        if not vertical_plan.question_header_indices:
            raise ManifestBuildError("Vertical manifest is missing question_header_indices.")

        local_key_indices = [index_map[idx] for idx in vertical_plan.record_key_indices]
        local_question_header_indices = [index_map[idx] for idx in vertical_plan.question_header_indices]
        local_answer_idx = index_map[answer_idx]
        local_metadata_indices = [index_map[idx] for idx in manifest.metadata_indices]
        key_columns = [
            self._make_output_column_name(original_columns[idx], idx)
            for idx in vertical_plan.record_key_indices
        ]
        record_df = pd.DataFrame(
            {
                self._make_output_column_name(original_columns[idx], idx): raw_df.iloc[:, index_map[idx]]
                for idx in vertical_plan.record_key_indices
            }
        )
        record_df["__question__"] = self.question_header_resolver.resolve(
            raw_df,
            local_question_header_indices,
        )
        record_df["__answer__"] = raw_df.iloc[:, local_answer_idx]
        record_df["__row_order__"] = range(len(raw_df))

        record_df = self.vertical_record_filter.drop_invalid_rows(
            record_df,
            key_columns=key_columns,
            question_column="__question__",
            answer_column="__answer__",
        )
        record_df = self.duplicate_answer_resolver.resolve(
            record_df,
            key_columns=key_columns,
            question_column="__question__",
            answer_column="__answer__",
            order_column="__row_order__",
        )

        answer_wide_df = self.vertical_record_assembler.assemble(
            record_df,
            key_columns=key_columns,
            question_column="__question__",
            answer_column="__answer__",
        )
        metadata_df = self.metadata_consolidator.consolidate(
            raw_df,
            key_indices=local_key_indices,
            metadata_indices=local_metadata_indices,
            column_name_builder=lambda _column_name, scoped_idx: self._make_output_column_name(
                original_columns[scoped_indices[scoped_idx]],
                scoped_indices[scoped_idx],
            ),
        )

        transformed_df = metadata_df.merge(answer_wide_df, on=key_columns, how="left")
        metadata_columns = self._metadata_output_columns(manifest, original_columns)
        verbatim_columns = [column for column in transformed_df.columns if column not in metadata_columns]
        return transformed_df[metadata_columns + verbatim_columns]

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
