import sys
import types
import unittest
from unittest.mock import patch

import pandas as pd

from app.services.language_normalization_service import EnglishTranslationBatchResult
from app.services.topic_label_ai_service import TopicAiLabelingBatchResult
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
            "assignments": [0, 0, 1],
            "warnings": ["KMeans test warning."],
        }


class _FakeBertopicService:
    def run(
        self,
        texts: list[str],
        embeddings,
        *,
        top_terms: int,
        language: str,
        reduce_outliers: bool,
        outlier_threshold: float,
    ) -> dict[str, object]:
        return {
            "assignments": [0, 0, 1],
            "groups": {
                "0": {
                    "terms": ["mai", "multe", "materiale"],
                    "is_noise": False,
                },
                "1": {
                    "terms": ["great", "website"],
                    "is_noise": False,
                },
            },
            "warnings": [],
        }


class _UnusedService:
    def run(self, *args, **kwargs):  # pragma: no cover - should not be called in the test path
        raise AssertionError("Unexpected service invocation")


class _FakeEnglishTranslationService:
    def __init__(self, translations: dict[str, str], warnings: list[str] | None = None) -> None:
        self.translations = translations
        self.warnings = list(warnings or [])
        self.calls: list[list[str]] = []

    def warm_up(self) -> None:
        return

    def translate(self, texts: list[str]) -> EnglishTranslationBatchResult:
        self.calls.append(list(texts))
        translated_texts: list[str] = []
        translated_flags: list[bool] = []
        detected_languages: list[str | None] = []

        for text in texts:
            translated_text = self.translations.get(text, text)
            translated_texts.append(translated_text)
            translated_flags.append(translated_text != text)
            detected_languages.append(None)

        translated_count = sum(1 for translated in translated_flags if translated)
        return EnglishTranslationBatchResult(
            texts=translated_texts,
            translated_flags=translated_flags,
            detected_languages=detected_languages,
            warnings=list(self.warnings),
            translated_count=translated_count,
        )


class _FakeAiLabelService:
    def __init__(self, labels_by_group_id: dict[str, str], warnings: list[str] | None = None) -> None:
        self.labels_by_group_id = labels_by_group_id
        self.warnings = list(warnings or [])

    def label_groups(self, groups: list[dict[str, object]], *, model_key: str, text_column_name: str) -> TopicAiLabelingBatchResult:
        return TopicAiLabelingBatchResult(
            labels_by_group_id=dict(self.labels_by_group_id),
            warnings=list(self.warnings),
            labeled_group_count=len(self.labels_by_group_id),
        )


class _FailingAiLabelService:
    def label_groups(self, groups: list[dict[str, object]], *, model_key: str, text_column_name: str) -> TopicAiLabelingBatchResult:
        raise TimeoutError("label timeout")


class _InspectableFakeBERTopic:
    last_instance = None

    def __init__(self, *args, **kwargs) -> None:
        type(self).last_instance = self
        self.updated_topics: list[int] | None = None
        self.reduce_kwargs: dict[str, object] = {}

    def fit_transform(self, texts: list[str], embeddings):
        return [-1, 0, 1], None

    def reduce_outliers(self, texts: list[str], topics: list[int], **kwargs):
        self.reduce_kwargs = dict(kwargs)
        return [0, 0, 1]

    def update_topics(self, texts: list[str], *, topics: list[int]) -> None:
        self.updated_topics = list(topics)

    def get_topic_info(self):
        if self.updated_topics == [0, 0, 1]:
            return pd.DataFrame([{"Topic": 0}, {"Topic": 1}])
        return pd.DataFrame([{"Topic": -1}, {"Topic": 0}, {"Topic": 1}])

    def get_topic(self, topic_id: int):
        if topic_id == 0:
            return [("confidence", 0.6), ("resources", 0.4)]
        if topic_id == 1:
            return [("website", 0.7), ("support", 0.3)]
        return [("confidence", 0.5)]


class _FakeClassTfidfTransformer:
    def __init__(self, *args, **kwargs) -> None:
        return


class _FakeUMAP:
    def __init__(self, *args, **kwargs) -> None:
        return


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
        self.assertEqual(prepared.translated_document_count, 0)

    def test_prepare_keeps_original_text_before_output_translation(self) -> None:
        dataframe = pd.DataFrame(
            {
                "verbatim": [
                    "Necesito mas recursos de matematicas",
                    "Need clearer instructions",
                ]
            }
        )

        service = TopicAnalysisTextPreparationService(
            max_document_chars=200,
            translation_service=_FakeEnglishTranslationService(
                {"Necesito mas recursos de matematicas": "Need more maths resources"}
            ),
        )
        prepared = service.prepare(dataframe, text_column_name="verbatim")

        self.assertEqual(prepared.translated_document_count, 0)
        self.assertEqual(
            prepared.texts,
            ["Necesito mas recursos de matematicas", "Need clearer instructions"],
        )
        self.assertEqual(prepared.documents[0].source_text, "Necesito mas recursos de matematicas")
        self.assertFalse(prepared.documents[0].translated_to_english)
        self.assertNotIn("Translated", " ".join(prepared.warnings))


class TopicAnalysisKeywordServiceTests(unittest.TestCase):
    def test_sanitize_terms_removes_stopwords_and_duplicate_tokens(self) -> None:
        service = TopicAnalysisKeywordService()

        terms = service.sanitize_terms(
            [
                "curriculum of",
                "search the search",
                "twinkl is twinkl",
                "to",
            ]
        )

        self.assertEqual(terms, ["curriculum", "search", "twinkl"])

    def test_top_ngrams_remove_stopwords_before_building_ngrams(self) -> None:
        service = TopicAnalysisKeywordService()

        ngrams = service.top_ngrams(
            [
                "What I am looking for is more of the resources in the classroom",
                "I am in the classroom and of the resources",
            ],
            ngram_size=1,
            top_n=10,
        )

        self.assertEqual([item["term"] for item in ngrams], ["resources", "classroom", "looking"])


class BertopicAnalysisServiceTests(unittest.TestCase):
    def test_run_reassigns_outliers_to_nearest_existing_theme(self) -> None:
        fake_bertopic_module = types.ModuleType("bertopic")
        fake_bertopic_module.BERTopic = _InspectableFakeBERTopic
        fake_vectorizers_module = types.ModuleType("bertopic.vectorizers")
        fake_vectorizers_module.ClassTfidfTransformer = _FakeClassTfidfTransformer
        fake_umap_module = types.ModuleType("umap")
        fake_umap_module.UMAP = _FakeUMAP

        service = BertopicAnalysisService()
        with patch.dict(
            sys.modules,
            {
                "bertopic": fake_bertopic_module,
                "bertopic.vectorizers": fake_vectorizers_module,
                "umap": fake_umap_module,
            },
        ):
            result = service.run(
                ["clear confidence response", "curriculum confidence", "website support"],
                [[0.1, 0.2], [0.2, 0.3], [0.8, 0.9]],
                top_terms=3,
                language="multilingual",
                reduce_outliers=True,
                outlier_threshold=0.0,
            )

        self.assertEqual(result["assignments"], [0, 0, 1])
        self.assertEqual(sorted(result["groups"].keys()), ["0", "1"])
        self.assertIn("BERTopic reassigned 1 response(s)", " ".join(result["warnings"]))
        self.assertEqual(_InspectableFakeBERTopic.last_instance.reduce_kwargs["strategy"], "embeddings")
        self.assertEqual(_InspectableFakeBERTopic.last_instance.reduce_kwargs["threshold"], 0.0)
        self.assertIsNotNone(_InspectableFakeBERTopic.last_instance.reduce_kwargs["embeddings"])


class TopicAnalysisServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        keyword_service = TopicAnalysisKeywordService()
        self.config = TopicAnalysisConfig(
            embedding_model="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            kmeans_clusters=4,
            kmeans_random_state=42,
            hdbscan_min_cluster_size=5,
            hdbscan_min_samples=3,
            hdbscan_metric="euclidean",
            bertopic_language="multilingual",
            bertopic_reduce_outliers=True,
            bertopic_outlier_threshold=0.0,
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

    def test_run_ngrams_translates_output_terms_only(self) -> None:
        service = TopicAnalysisService(
            config=self.config,
            input_validation_service=self.validation_service,
            text_preparation_service=TopicAnalysisTextPreparationService(
                max_document_chars=300,
                translation_service=_FakeEnglishTranslationService(
                    {
                        "necesito": "need",
                        "recursos": "resources",
                        "matematicas": "maths",
                    }
                ),
            ),
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
                    "Necesito recursos matematicas",
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
        self.assertGreaterEqual(result["translated_document_count"], 1)
        self.assertIsNone(result["error"])
        self.assertEqual(len(result["ngram_buckets"]), 3)
        self.assertEqual(result["ngram_buckets"][0]["label"], "Single Words")
        self.assertGreaterEqual(len(result["ngram_buckets"][0]["items"]), 1)
        self.assertTrue(any(item.get("translated") for item in result["ngram_buckets"][0]["items"]))
        self.assertIn("Translated", " ".join(result["warnings"]))

    def test_run_ngrams_keeps_translated_display_terms_stopword_free(self) -> None:
        service = TopicAnalysisService(
            config=self.config,
            input_validation_service=self.validation_service,
            text_preparation_service=TopicAnalysisTextPreparationService(
                max_document_chars=300,
                translation_service=_FakeEnglishTranslationService(
                    {
                        "aula": "in the classroom",
                    }
                ),
            ),
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
                "verbatim": [
                    "aula",
                    "aula",
                    "aula",
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
        self.assertEqual(result["ngram_buckets"][0]["items"][0]["term"], "classroom")

    def test_run_ngrams_includes_matching_documents_for_each_item(self) -> None:
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
                "verbatim": [
                    "Need more science resources",
                    "More science resources help",
                    "Need more maths resources",
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

        bigram_items = result["ngram_buckets"][1]["items"]
        matching_item = next(item for item in bigram_items if item["term"] == "science resources")
        self.assertEqual(matching_item["count"], 2)
        self.assertEqual(matching_item["document_count"], 2)
        self.assertEqual(
            matching_item["_documents"],
            [
                {"row_number": 1, "text": "Need more science resources"},
                {"row_number": 2, "text": "More science resources help"},
            ],
        )

    def test_run_kmeans_translates_group_outputs_after_grouping(self) -> None:
        service = TopicAnalysisService(
            config=self.config,
            input_validation_service=self.validation_service,
            text_preparation_service=TopicAnalysisTextPreparationService(
                max_document_chars=300,
                translation_service=_FakeEnglishTranslationService(
                    {
                        "Responses about ayuda docente": "Responses about teaching support",
                        "ayuda docente": "teaching support",
                    }
                ),
            ),
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
                    "ayuda docente",
                    "ayuda docente",
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
        self.assertEqual(result["groups"][0]["label"], "Responses about teaching support")
        self.assertEqual(result["groups"][0]["source_label"], "Responses about ayuda docente")
        self.assertTrue(result["groups"][0]["translated"])
        self.assertGreaterEqual(len(result["groups"][0]["examples"]), 1)
        self.assertTrue(result["groups"][0]["examples"][0]["translated"])
        self.assertEqual(result["groups"][0]["examples"][0]["source_text"], "ayuda docente")
        self.assertIn("Representative document", result["groups"][0]["comment"])
        self.assertIn("KMeans test warning.", result["warnings"])
        self.assertGreaterEqual(result["translated_document_count"], 2)

    def test_run_kmeans_can_replace_heuristic_labels_with_ai_labels_without_retranslating_them(self) -> None:
        translation_service = _FakeEnglishTranslationService(
            {
                "ayuda docente": "teaching support",
            }
        )
        service = TopicAnalysisService(
            config=self.config,
            input_validation_service=self.validation_service,
            text_preparation_service=TopicAnalysisTextPreparationService(
                max_document_chars=300,
                translation_service=translation_service,
            ),
            keyword_service=self.keyword_service,
            narrative_service=self.narrative_service,
            representative_example_service=self.example_service,
            embedding_service=_FakeEmbeddingService(),
            ngram_service=self.ngram_service,
            kmeans_service=_FakeKMeansService(),
            hdbscan_service=_UnusedService(),
            bertopic_service=_UnusedService(),
            ai_label_service=_FakeAiLabelService({"0": "Teaching Support"}),
        )
        dataframe = pd.DataFrame(
            {
                "verbatim": [
                    "ayuda docente",
                    "ayuda docente",
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
        self.assertEqual(result["groups"][0]["label"], "Teaching Support")
        self.assertEqual(result["groups"][0]["source_label"], "Responses about ayuda docente")
        self.assertTrue(result["groups"][0]["ai_generated"])
        self.assertFalse(result["groups"][0]["translated"])
        self.assertTrue(all("Teaching Support" not in batch for batch in translation_service.calls))
        self.assertIn("AI generated clearer labels", " ".join(result["warnings"]))

    def test_run_bertopic_translates_mixed_language_theme_names_before_display(self) -> None:
        service = TopicAnalysisService(
            config=self.config,
            input_validation_service=self.validation_service,
            text_preparation_service=TopicAnalysisTextPreparationService(
                max_document_chars=300,
                translation_service=_FakeEnglishTranslationService(
                    {
                        "am nevoie de mai multe materiale": "I need more materials",
                        "mai multe materiale": "more materials",
                        "mai": "more",
                        "multe": "more",
                        "materiale": "materials",
                    }
                ),
            ),
            keyword_service=self.keyword_service,
            narrative_service=self.narrative_service,
            representative_example_service=self.example_service,
            embedding_service=_FakeEmbeddingService(),
            ngram_service=self.ngram_service,
            kmeans_service=_UnusedService(),
            hdbscan_service=_UnusedService(),
            bertopic_service=_FakeBertopicService(),
        )
        dataframe = pd.DataFrame(
            {
                "verbatim": [
                    "am nevoie de mai multe materiale",
                    "mai multe materiale",
                    "great website",
                ]
            }
        )

        result = service.run(
            result_id="abc123",
            dataframe=dataframe,
            model_key="bertopic",
            text_column_name="verbatim",
            available_verbatim_columns=["verbatim"],
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["groups"][0]["label"], "Requests for materials")
        self.assertEqual(result["groups"][0]["source_label"], "Responses about mai multe")
        self.assertTrue(result["groups"][0]["translated"])
        self.assertIn("materials", result["groups"][0]["terms"])
        self.assertNotIn("more", result["groups"][0]["terms"])
        self.assertNotIn("mai", result["groups"][0]["label"])

    def test_run_keeps_heuristic_labels_when_ai_labeling_fails(self) -> None:
        service = TopicAnalysisService(
            config=self.config,
            input_validation_service=self.validation_service,
            text_preparation_service=TopicAnalysisTextPreparationService(max_document_chars=300),
            keyword_service=self.keyword_service,
            narrative_service=self.narrative_service,
            representative_example_service=self.example_service,
            embedding_service=_FakeEmbeddingService(),
            ngram_service=self.ngram_service,
            kmeans_service=_FakeKMeansService(),
            hdbscan_service=_UnusedService(),
            bertopic_service=_UnusedService(),
            ai_label_service=_FailingAiLabelService(),
        )
        dataframe = pd.DataFrame(
            {
                "verbatim": [
                    "Need more classroom materials",
                    "Need more classroom materials",
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
        self.assertFalse(result["groups"][0]["ai_generated"])
        self.assertEqual(result["groups"][0]["label"], "Requests for classroom materials")
        self.assertIn("AI topic labeling was skipped", " ".join(result["warnings"]))

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
