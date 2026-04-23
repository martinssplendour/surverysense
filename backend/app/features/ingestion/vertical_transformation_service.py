from __future__ import annotations

import pandas as pd

from app.core.exceptions import ManifestBuildError


class VerticalTransformationService:
    def __init__(
        self,
        *,
        question_header_resolver,
        vertical_record_filter,
        duplicate_answer_resolver,
        metadata_consolidator,
        vertical_record_assembler,
    ) -> None:
        self.question_header_resolver = question_header_resolver
        self.vertical_record_filter = vertical_record_filter
        self.duplicate_answer_resolver = duplicate_answer_resolver
        self.metadata_consolidator = metadata_consolidator
        self.vertical_record_assembler = vertical_record_assembler

    def build(
        self,
        raw_df: pd.DataFrame,
        manifest,
        *,
        original_columns: pd.Index,
        scoped_indices: list[int],
        index_map: dict[int, int],
        metadata_output_columns,
        make_output_column_name,
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
            make_output_column_name(original_columns[idx], idx)
            for idx in vertical_plan.record_key_indices
        ]
        record_df = pd.DataFrame(
            {
                make_output_column_name(original_columns[idx], idx): raw_df.iloc[:, index_map[idx]]
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
            column_name_builder=lambda _column_name, scoped_idx: make_output_column_name(
                original_columns[scoped_indices[scoped_idx]],
                scoped_indices[scoped_idx],
            ),
        )

        transformed_df = metadata_df.merge(answer_wide_df, on=key_columns, how="left")
        verbatim_columns = [column for column in transformed_df.columns if column not in metadata_output_columns]
        return transformed_df[metadata_output_columns + verbatim_columns]
