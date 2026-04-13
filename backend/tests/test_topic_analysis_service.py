import unittest

import pandas as pd

from app.services.topic_analysis_services import (
    BertopicAnalysisService,
    HdbscanAnalysisService,
    KMeansAnalysisService,
    NgramAnalysisService,
    RepresentativeExampleSelectionService,
    SentenceEmbeddingService,
    TopicAnalysisConfig,
    TopicAnalysisInputValidationService,
    TopicAnalysisKeywordService,
    TopicAnalysisNarrativeService,
    TopicAnalysisService,
    TopicAnalysisTextPreparationService,
)


class _FakeEmbeddingService:
    def encode(self, texts: list[str], *, model_name: str):
        return [[float(index), float(index + 1)] for index, _text in enumerate(texts)]


class _FakeKMeansService:
    def run(self, embeddings, *, requested_clusters: int, random_state: int) -> dict[str, object]:
        return {
            "assignments": [0, 1, 0],
            "warnings": ["KMeans test warning."],
        }


class _UnusedService:
    def run(self, *args, **kwargs):  # pragma: no cover - should not be called in the test path
        raise AssertionError("Unexpected service invocation")


class TopicAnalysisTextPreparationServiceTests(unittest.TestCase):
    def test_prepare_skips_nan_placeholder_and_blank_values(self) -> None:
        dataframe = pd.DataFrame(
            {
                "verbatim": [
                    None,
                    "   ",
                    "NaN",
                    "Need more maths worksheets",
                    "Need clearer instructions",
                ]
            }
        )

        service = TopicAnalysisTextPreparationService(max_document_chars=200)
        prepared = service.prepare(dataframe, text_column_name="verbatim")

        self.assertEqual(prepared.total_row_count, 5)
        self.assertEqual(prepared.skipped_row_count, 3)
        self.assertEqual(
            prepared.texts,
            ["Need more maths worksheets", "Need clearer instructions"],
        )
        self.assertIn("Skipped 3 empty or NaN row(s) before analysis.", prepared.warnings)


class TopicAnalysisServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        keyword_service = TopicAnalysisKeywordService()
        self.config = TopicAnalysisConfig(
            embedding_model="sentence-transformers/all-mpnet-base-v2",
            kmeans_clusters=4,
            kmeans_random_state=42,
            hdbscan_min_cluster_size=5,
            hdbscan_min_samples=3,
            hdbscan_metric="euclidean",
            bertopic_language="multilingual",
            top_terms_per_group=5,
            top_ngrams_per_bucket=6,
            representative_examples_per_group=2,
            max_document_chars=300,
        )
        self.validation_service = TopicAnalysisInputValidationService()
        self.text_preparation_service = TopicAnalysisTextPreparationService(max_document_chars=300)
        self.keyword_service = keyword_service
        self.narrative_service = TopicAnalysisNarrativeService(keyword_service)
        self.example_service = RepresentativeExampleSelectionService()
        self.ngram_service = NgramAnalysisService(keyword_service)

    def test_run_ngrams_returns_structured_buckets(self) -> None:
        service = TopicAnalysisService(
            config=self.config,
            input_validation_service=self.validation_service,
            text_preparation_service=self.text_preparation_service,
            keyword_service=self.keyword_service,
            narrative_service=self.narrative_service,
            representative_example_service=self.example_service,
            embedding_service=_FakeEmbeddingService(),
            ngram_service=self.ngram_service,
            kmeans_service=_UnusedService(),
            hdbscan_service=_UnusedService(),
            bertopic_service=_UnusedService(),
        )
        dataframe = pd.DataFrame(
            {
                "country__idx_1": ["UK", "UK", "US"],
                "verbatim": [
                    "Need more maths worksheets",
                    None,
                    "Need more science worksheets",
                ],
            }
        )

        result = service.run(
            result_id="abc123",
            dataframe=dataframe,
            model_key="ngrams",
            text_column_name="verbatim",
            available_verbatim_columns=["verbatim"],
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["valid_document_count"], 2)
        self.assertEqual(result["skipped_document_count"], 1)
        self.assertIsNone(result["error"])
        self.assertEqual(len(result["ngram_buckets"]), 3)
        self.assertEqual(result["ngram_buckets"][0]["label"], "Single Words")
        self.assertGreaterEqual(len(result["ngram_buckets"][0]["items"]), 1)

    def test_run_kmeans_builds_group_cards_from_assignments(self) -> None:
        service = TopicAnalysisService(
            config=self.config,
            input_validation_service=self.validation_service,
            text_preparation_service=self.text_preparation_service,
            keyword_service=self.keyword_service,
            narrative_service=self.narrative_service,
            representative_example_service=self.example_service,
            embedding_service=_FakeEmbeddingService(),
            ngram_service=self.ngram_service,
            kmeans_service=_FakeKMeansService(),
            hdbscan_service=_UnusedService(),
            bertopic_service=_UnusedService(),
        )
        dataframe = pd.DataFrame(
            {
                "verbatim": [
                    "Need more maths resources for year 3",
                    "Need better phonics resources",
                    "More maths challenge activities would help",
                ]
            }
        )

        result = service.run(
            result_id="abc123",
            dataframe=dataframe,
            model_key="kmeans",
            text_column_name="verbatim",
            available_verbatim_columns=["verbatim"],
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["model_label"], "Response Groups")
        self.assertEqual(len(result["groups"]), 2)
        self.assertEqual(result["groups"][0]["count"], 2)
        self.assertIn("Representative document", result["groups"][0]["comment"])
        self.assertNotIn("/", result["groups"][0]["label"])
        self.assertGreaterEqual(len(result["groups"][0]["examples"]), 1)
        self.assertIn("KMeans test warning.", result["warnings"])

    def test_invalid_column_returns_structured_error_response(self) -> None:
        service = TopicAnalysisService(
            config=self.config,
            input_validation_service=self.validation_service,
            text_preparation_service=self.text_preparation_service,
            keyword_service=self.keyword_service,
            narrative_service=self.narrative_service,
            representative_example_service=self.example_service,
            embedding_service=SentenceEmbeddingService(),
            ngram_service=self.ngram_service,
            kmeans_service=KMeansAnalysisService(),
            hdbscan_service=HdbscanAnalysisService(),
            bertopic_service=BertopicAnalysisService(),
        )
        dataframe = pd.DataFrame({"verbatim": ["Need more resources"]})

        result = service.run(
            result_id="abc123",
            dataframe=dataframe,
            model_key="ngrams",
            text_column_name="wrong_column",
            available_verbatim_columns=["verbatim"],
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["valid_document_count"], 0)
        self.assertIn("Choose one of the detected verbatim columns", result["error"])


if __name__ == "__main__":
    unittest.main()
