import unittest

import pandas as pd

from app.services.metadata_filter_service import MetadataFilterService
from app.services.result_store_service import ResultNotFoundError, ResultStoreService


class ResultStoreServiceTests(unittest.TestCase):
    def test_save_and_get_page_returns_requested_slice(self) -> None:
        service = ResultStoreService(MetadataFilterService(), max_results=2)
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
        service = ResultStoreService(MetadataFilterService(), max_results=2)
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

    def test_get_page_raises_for_missing_result(self) -> None:
        service = ResultStoreService(MetadataFilterService())

        with self.assertRaises(ResultNotFoundError):
            service.get_page("missing", dataset="analysis", offset=0, limit=10)


if __name__ == "__main__":
    unittest.main()
