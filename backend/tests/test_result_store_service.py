import unittest

import pandas as pd

from app.services.cleaning_services import (
    AnalysisReadyDatasetService,
    MetadataColumnSelectionService,
    MultipartVerbatimConsolidationService,
    TextNormalizationService,
    VerbatimQuestionSelectionService,
    VerbatimRowFilterService,
)
from app.services.metadata_filter_service import MetadataFilterService
from app.services.result_store_service import ResultNotFoundError, ResultStoreService


class ResultStoreServiceTests(unittest.TestCase):
    def build_service(self) -> ResultStoreService:
        text_normalizer = TextNormalizationService()
        analysis_ready_service = AnalysisReadyDatasetService(
            metadata_selector=MetadataColumnSelectionService(),
            verbatim_selector=VerbatimQuestionSelectionService(),
            multipart_verbatim_consolidator=MultipartVerbatimConsolidationService(text_normalizer),
            row_filter=VerbatimRowFilterService(),
        )
        return ResultStoreService(
            MetadataFilterService(),
            analysis_ready_service=analysis_ready_service,
            max_results=2,
        )

    def test_save_and_get_page_returns_requested_slice(self) -> None:
        service = self.build_service()
        transformed_df = pd.DataFrame(
            [
                {"country__idx_1": "UK", "col_a": "row1", "col_b": "A"},
                {"country__idx_1": "US", "col_a": "row2", "col_b": "B"},
                {"country__idx_1": "UK", "col_a": "row3", "col_b": "C"},
            ]
        )
        analysis_df = pd.DataFrame(
            [
                {"country__idx_1": "UK", "verbatim": "v1"},
                {"country__idx_1": "US", "verbatim": "v2"},
            ]
        )

        result_id = service.save(
            transformed_df,
            analysis_df,
            metadata_columns=["country__idx_1"],
            verbatim_columns=["verbatim"],
        )
        page = service.get_page(result_id, dataset="transformed", offset=1, limit=2)

        self.assertEqual(page.result_id, result_id)
        self.assertEqual(page.dataset, "transformed")
        self.assertEqual(page.total_row_count, 3)
        self.assertEqual(page.unfiltered_row_count, 3)
        self.assertEqual(page.offset, 1)
        self.assertEqual(page.limit, 2)
        self.assertFalse(page.has_more)
        self.assertEqual(page.column_names, ["country__idx_1", "col_a", "col_b"])
        self.assertEqual(
            page.rows,
            [
                {"country__idx_1": "US", "col_a": "row2", "col_b": "B"},
                {"country__idx_1": "UK", "col_a": "row3", "col_b": "C"},
            ],
        )

    def test_get_page_can_filter_by_metadata_value(self) -> None:
        service = self.build_service()
        transformed_df = pd.DataFrame(
            [
                {"country__idx_1": "UK", "county__idx_2": "Kent", "answer": "A"},
                {"country__idx_1": "US", "county__idx_2": "King", "answer": "B"},
                {"country__idx_1": "UK", "county__idx_2": "Essex", "answer": "C"},
            ]
        )
        analysis_df = transformed_df.copy()

        result_id = service.save(
            transformed_df,
            analysis_df,
            metadata_columns=["country__idx_1", "county__idx_2"],
            verbatim_columns=["answer"],
        )
        page = service.get_page(
            result_id,
            dataset="transformed",
            offset=0,
            limit=10,
            filters={"country__idx_1": ["UK"]},
        )

        self.assertEqual(page.total_row_count, 2)
        self.assertEqual(page.unfiltered_row_count, 3)
        self.assertEqual(
            page.rows,
            [
                {"country__idx_1": "UK", "county__idx_2": "Kent", "answer": "A"},
                {"country__idx_1": "UK", "county__idx_2": "Essex", "answer": "C"},
            ],
        )

    def test_get_dataset_returns_filtered_analysis_context(self) -> None:
        service = self.build_service()
        transformed_df = pd.DataFrame(
            [
                {"country__idx_1": "UK", "verbatim": "Need more maths"},
                {"country__idx_1": "US", "verbatim": "Need more science"},
            ]
        )
        analysis_df = transformed_df.copy()

        result_id = service.save(
            transformed_df,
            analysis_df,
            metadata_columns=["country__idx_1"],
            verbatim_columns=["verbatim"],
        )
        selection = service.get_dataset(
            result_id,
            dataset="analysis",
            filters={"country__idx_1": ["UK"]},
        )

        self.assertEqual(selection.result_id, result_id)
        self.assertEqual(selection.dataset, "analysis")
        self.assertEqual(selection.total_row_count, 2)
        self.assertEqual(selection.metadata_columns, ["country__idx_1"])
        self.assertEqual(selection.verbatim_columns, ["verbatim"])
        self.assertEqual(
            selection.dataframe.to_dict(orient="records"),
            [{"country__idx_1": "UK", "verbatim": "Need more maths"}],
        )

    def test_get_page_raises_for_missing_result(self) -> None:
        service = self.build_service()

        with self.assertRaises(ResultNotFoundError):
            service.get_page("missing", dataset="analysis", offset=0, limit=10)

    def test_update_column_role_rebuilds_analysis_and_filters(self) -> None:
        service = self.build_service()
        transformed_df = pd.DataFrame(
            [
                {
                    "country__idx_1": "UK",
                    "segment__idx_2": "Primary",
                    "comment_a": "Need more phonics",
                    "comment_b": None,
                },
                {
                    "country__idx_1": "US",
                    "segment__idx_2": "Secondary",
                    "comment_a": None,
                    "comment_b": "Need more maths",
                },
            ]
        )
        analysis_df = pd.DataFrame(
            [
                {"country__idx_1": "UK", "comment_a": "Need more phonics"},
            ]
        )

        result_id = service.save(
            transformed_df,
            analysis_df,
            metadata_columns=["country__idx_1"],
            verbatim_columns=["comment_a"],
        )

        updated = service.update_column_role(
            result_id,
            column_name="segment__idx_2",
            role="metadata",
        )
        self.assertEqual(updated.metadata_columns, ["country__idx_1", "segment__idx_2"])

        updated = service.update_column_role(
            result_id,
            column_name="comment_b",
            role="verbatim",
        )
        self.assertEqual(updated.verbatim_columns, ["comment_a", "comment_b"])
        self.assertEqual(
            updated.analysis_df.to_dict(orient="records"),
            [
                {"country__idx_1": "UK", "segment__idx_2": "Primary", "comment_a": "Need more phonics", "comment_b": None},
                {"country__idx_1": "US", "segment__idx_2": "Secondary", "comment_a": None, "comment_b": "Need more maths"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
