import unittest

import pandas as pd
from app.services.metadata_filter_service import MetadataFilterService


class MetadataFilterServiceTests(unittest.TestCase):
    def test_build_definitions_keeps_low_cardinality_metadata_columns(self) -> None:
        service = MetadataFilterService()
        df = pd.DataFrame(
            [
                {
                    "response_id__idx_0": "resp-1",
                    "country__idx_1": "UK",
                    "county__idx_2": "Kent",
                    "survey_month__idx_3": "2026-02",
                },
                {
                    "response_id__idx_0": "resp-2",
                    "country__idx_1": "US",
                    "county__idx_2": "King",
                    "survey_month__idx_3": "2026-02",
                },
                {
                    "response_id__idx_0": "resp-3",
                    "country__idx_1": "UK",
                    "county__idx_2": "Kent",
                    "survey_month__idx_3": "2026-03",
                },
            ]
        )

        definitions = service.build_definitions(
            df,
            metadata_columns=[
                "response_id__idx_0",
                "country__idx_1",
                "county__idx_2",
                "survey_month__idx_3",
            ],
        )

        self.assertEqual(
            [definition.column_name for definition in definitions],
            ["country__idx_1", "county__idx_2", "survey_month__idx_3"],
        )
        self.assertEqual(definitions[0].display_name, "Country")
        self.assertEqual(
            [(option.value, option.count) for option in definitions[0].options],
            [("UK", 2), ("US", 1)],
        )

    def test_apply_filters_returns_intersection_of_selected_values(self) -> None:
        service = MetadataFilterService()
        df = pd.DataFrame(
            [
                {"country__idx_1": "UK", "county__idx_2": "Kent", "answer": "A"},
                {"country__idx_1": "UK", "county__idx_2": "Essex", "answer": "B"},
                {"country__idx_1": "US", "county__idx_2": "King", "answer": "C"},
            ]
        )

        filtered = service.apply_filters(
            df,
            filters={
                "country__idx_1": ["UK"],
                "county__idx_2": ["Kent"],
            },
            allowed_columns={"country__idx_1", "county__idx_2"},
        )

        self.assertEqual(
            filtered.to_dict(orient="records"),
            [{"country__idx_1": "UK", "county__idx_2": "Kent", "answer": "A"}],
        )

    def test_filter_options_use_exact_unique_values_without_merging(self) -> None:
        service = MetadataFilterService()
        df = pd.DataFrame(
            [
                {"country__idx_1": "UK", "answer": "A"},
                {"country__idx_1": " UK", "answer": "B"},
                {"country__idx_1": "UK ", "answer": "C"},
                {"country__idx_1": "", "answer": "D"},
            ]
        )

        definitions = service.build_definitions(df, metadata_columns=["country__idx_1"])

        self.assertEqual(len(definitions), 1)
        self.assertEqual(
            [(option.value, option.count) for option in definitions[0].options],
            [("UK", 1), (" UK", 1), ("UK ", 1)],
        )


if __name__ == "__main__":
    unittest.main()
