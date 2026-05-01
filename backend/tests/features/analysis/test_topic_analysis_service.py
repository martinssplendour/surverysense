import sys
import types
import unittest
from unittest.mock import patch

import pandas as pd
from app.core.exceptions import TopicAnalysisDependencyError, TopicAnalysisRateLimitError
from app.features.analysis.language_normalization_service import EnglishTranslationBatchResult
from app.features.analysis.topic_analysis_services import (
    CommunityDetectionAnalysisService,
    NgramAnalysisService,
    RepresentativeExampleSelectionService,
    SentenceEmbeddingService,
    TopicAnalysisConfig,
    TopicAnalysisInputValidationService,
    TopicAnalysisKeywordService,
    TopicAnalysisNarrativeService,
    TopicAnalysisService,
    TopicAnalysisTextPreparationService,
    TopicModelRunResult,
)
from app.features.analysis.topic_analysis_services.execution import TopicModelExecutionService
from app.features.analysis.topic_label_ai_service import TopicAiLabelingBatchResult
from app.models.enums import AnalysisModelKey


class _FakeEmbeddingService:
    last_texts: list[str] = []

    def encode(self, texts: list[str], **kwargs):
        type(self).last_texts = list(texts)
        return [[float(index), float(index + 1)] for index, _text in enumerate(texts)]

    def warm_up(self, *args, **kwargs) -> None:
        return


class _FakeCommunityDetectionService:
    def run(
        self,
        embeddings,
        *,
        similarity_threshold: float,
        max_neighbors: int,
        resolution: float = 1.0,
        mutual_neighbors: bool = True,
        languages: list[str | None] | None = None,
    ) -> TopicModelRunResult:
        return TopicModelRunResult(
            assignments=[0, 0, 1],
            warnings=["Community detection test warning."],
            network_edges=[(0, 1, 0.95)],
            layout_positions={0: (0.0, 0.0), 1: (0.2, 0.1), 2: (1.0, 1.0)},
    )


class _EmbeddingPassthroughCommunityService:
    def run(
        self,
        embeddings,
        *,
        similarity_threshold: float,
        max_neighbors: int,
        resolution: float = 1.0,
        mutual_neighbors: bool = True,
        languages: list[str | None] | None = None,
    ) -> TopicModelRunResult:
        return TopicModelRunResult(assignments=[0 for _embedding in embeddings], warnings=[])


class _SingleCommunityDetectionService:
    def run(
        self,
        embeddings,
        *,
        similarity_threshold: float,
        max_neighbors: int,
        resolution: float = 1.0,
        mutual_neighbors: bool = True,
        languages: list[str | None] | None = None,
    ) -> TopicModelRunResult:
        return TopicModelRunResult(assignments=[0 for _embedding in embeddings], warnings=[])


class _CentralCommunityDetectionService:
    def run(
        self,
        embeddings,
        *,
        similarity_threshold: float,
        max_neighbors: int,
        resolution: float = 1.0,
        mutual_neighbors: bool = True,
        languages: list[str | None] | None = None,
    ) -> TopicModelRunResult:
        return TopicModelRunResult(
            assignments=[0 for _embedding in embeddings],
            warnings=[],
            network_edges=[
                (2, 1, 0.95),
                (2, 3, 0.95),
                (1, 3, 0.5),
                (2, 0, 0.2),
                (0, 1, 0.1),
            ],
        )


class _DuplicateLabelCommunityDetectionService:
    def run(
        self,
        embeddings,
        *,
        similarity_threshold: float,
        max_neighbors: int,
        resolution: float = 1.0,
        mutual_neighbors: bool = True,
        languages: list[str | None] | None = None,
    ) -> TopicModelRunResult:
        return TopicModelRunResult(
            assignments=[0, 0, 1, 1],
            warnings=[],
            network_edges=[(0, 1, 0.9), (2, 3, 0.9)],
            layout_positions={
                0: (0.0, 0.0),
                1: (0.1, 0.1),
                2: (1.0, 1.0),
                3: (1.1, 1.1),
            },
        )


class _FakeFallbackEmbeddingService:
    calls: list[str] = []

    def encode(self, texts: list[str], **kwargs):
        provider = kwargs.get("provider", "")
        type(self).calls.append(str(provider))
        if provider == "gemini":
            raise TopicAnalysisDependencyError("Gemini embeddings request failed (429): Resource exhausted.")
        return [[1.0, 0.0] for _text in texts]

    def warm_up(self, *args, **kwargs) -> None:
        return


class _FakeRateLimitedEmbeddingService:
    def encode(self, texts: list[str], **kwargs):
        raise TopicAnalysisRateLimitError(
            "Gemini is rate limited. Try again later.",
            error_code="gemini_rate_limited",
            retry_after_seconds=60,
        )

    def warm_up(self, *args, **kwargs) -> None:
        return


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

    def detect_languages(self, texts: list[str]) -> EnglishTranslationBatchResult:
        return EnglishTranslationBatchResult(
            texts=list(texts),
            translated_flags=[False] * len(texts),
            detected_languages=["es" if text in self.translations else "en" for text in texts],
            warnings=[],
            translated_count=0,
        )


class _FakeAiLabelService:
    def __init__(self, labels_by_group_id: dict[str, str], warnings: list[str] | None = None) -> None:
        self.labels_by_group_id = labels_by_group_id
        self.warnings = list(warnings or [])

    def label_groups(self, groups, *, model_key, text_column_name) -> TopicAiLabelingBatchResult:
        return TopicAiLabelingBatchResult(
            labels_by_group_id=dict(self.labels_by_group_id),
            warnings=list(self.warnings),
            labeled_group_count=len(self.labels_by_group_id),
        )


class _FailingAiLabelService:
    def label_groups(self, groups, *, model_key, text_column_name) -> TopicAiLabelingBatchResult:
        raise TimeoutError("label timeout")


class _FakeEmbeddingResponse:
    def __init__(
        self,
        payload: dict[str, object],
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = ""
        self.headers = headers or {}

    def json(self):
        return self._payload


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

    def test_prepare_translates_non_english_texts_before_embedding(self) -> None:
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

        self.assertEqual(prepared.translated_document_count, 1)
        self.assertEqual(
            prepared.texts,
            ["Need more maths resources", "Need clearer instructions"],
        )
        self.assertEqual(prepared.documents[0].text, "Need more maths resources")
        self.assertEqual(prepared.documents[0].source_text, "Necesito mas recursos de matematicas")
        self.assertTrue(prepared.documents[0].translated_to_english)
        self.assertFalse(prepared.documents[1].translated_to_english)

    def test_prepare_detects_language_without_translating_when_input_translation_is_disabled(self) -> None:
        dataframe = pd.DataFrame(
            {
                "verbatim": [
                    "Necesito mas recursos de matematicas",
                    "Need clearer instructions",
                ]
            }
        )
        translation_service = _FakeEnglishTranslationService(
            {"Necesito mas recursos de matematicas": "Need more maths resources"}
        )

        service = TopicAnalysisTextPreparationService(
            max_document_chars=200,
            translation_service=translation_service,
            input_translation_enabled=False,
        )
        prepared = service.prepare(dataframe, text_column_name="verbatim")

        self.assertEqual(prepared.texts, ["Necesito mas recursos de matematicas", "Need clearer instructions"])
        self.assertEqual(prepared.translated_document_count, 0)
        self.assertEqual(prepared.documents[0].detected_language, "es")
        self.assertEqual(prepared.documents[1].detected_language, "en")
        self.assertEqual(translation_service.calls, [])

    def test_prepare_skips_single_word_responses_before_embedding(self) -> None:
        dataframe = pd.DataFrame(
            {
                "verbatim": [
                    "CVV",
                    "cost",
                    "Need clearer resources",
                    "ccc",
                    "cost",
                ]
            }
        )

        service = TopicAnalysisTextPreparationService(max_document_chars=200)
        prepared = service.prepare(dataframe, text_column_name="verbatim")

        self.assertEqual(
            prepared.texts,
            ["Need clearer resources"],
        )
        self.assertEqual(prepared.skipped_row_count, 4)
        self.assertEqual(prepared.original_response_count, 1)
        self.assertIn("Skipped 4 single-word response(s) before analysis.", prepared.warnings)

    def test_prepare_sentencizes_multi_sentence_responses_for_embedding(self) -> None:
        dataframe = pd.DataFrame(
            {
                "verbatim": [
                    "Need more maths challenge resources. Would like clearer worked examples.",
                    "Need better reading resources, Would like more phonics examples",
                    "The website is useful.",
                ]
            }
        )

        service = TopicAnalysisTextPreparationService(max_document_chars=200)
        prepared = service.prepare(dataframe, text_column_name="verbatim")

        self.assertEqual(
            prepared.texts,
            [
                "Need more maths challenge resources.",
                "Would like clearer worked examples.",
                "Need better reading resources",
                "Would like more phonics examples",
                "The website is useful.",
            ],
        )
        self.assertEqual(prepared.original_response_count, 3)
        self.assertEqual([document.row_number for document in prepared.documents], [1, 1, 2, 2, 3])

    def test_prepare_does_not_sentencize_short_or_mixed_punctuation_sentences(self) -> None:
        dataframe = pd.DataFrame(
            {
                "verbatim": [
                    "Yes. Need more maths challenge resources.",
                    "Need more maths challenge resources! Would like clearer worked examples.",
                    "Yes, Need more maths challenge resources",
                    "As a Pastoral Lead, I need quick access to age appropriate resources.",
                ]
            }
        )

        service = TopicAnalysisTextPreparationService(max_document_chars=200)
        prepared = service.prepare(dataframe, text_column_name="verbatim")

        self.assertEqual(
            prepared.texts,
            [
                "Yes. Need more maths challenge resources.",
                "Need more maths challenge resources! Would like clearer worked examples.",
                "Yes, Need more maths challenge resources",
                "As a Pastoral Lead, I need quick access to age appropriate resources.",
            ],
        )

    def test_prepare_merges_connector_sentences_with_previous_chunk(self) -> None:
        dataframe = pd.DataFrame(
            {
                "verbatim": [
                    "The search is difficult. So better filters would help.",
                    "The platform is useful. But clearer labels would build confidence. More examples would help teachers.",
                    "The resources are helpful. However, curriculum links would improve confidence. Because teachers need evidence.",
                ]
            }
        )

        service = TopicAnalysisTextPreparationService(max_document_chars=300)
        prepared = service.prepare(dataframe, text_column_name="verbatim")

        self.assertEqual(
            prepared.texts,
            [
                "The search is difficult. So better filters would help.",
                "The platform is useful. But clearer labels would build confidence.",
                "More examples would help teachers.",
                "The resources are helpful. However, curriculum links would improve confidence. Because teachers need evidence.",
            ],
        )

    def test_prepare_keeps_and_sentences_as_separate_chunks(self) -> None:
        dataframe = pd.DataFrame(
            {
                "verbatim": [
                    "The resources are useful. And clearer curriculum links would help.",
                ]
            }
        )

        service = TopicAnalysisTextPreparationService(max_document_chars=300)
        prepared = service.prepare(dataframe, text_column_name="verbatim")

        self.assertEqual(
            prepared.texts,
            [
                "The resources are useful.",
                "And clearer curriculum links would help.",
            ],
        )


class TopicAnalysisKeywordServiceTests(unittest.TestCase):
    def test_sanitize_terms_removes_stopwords_and_duplicate_tokens(self) -> None:
        service = TopicAnalysisKeywordService()

        terms = service.sanitize_terms(
            [
                "curriculum of",
                "search the search",
                "twinkl is twinkl",
                "using resources",
                "to",
            ]
        )

        self.assertEqual(terms, ["curriculum", "search", "twinkl", "resources"])

    def test_top_ngrams_remove_stopwords_before_building_ngrams(self) -> None:
        service = TopicAnalysisKeywordService()

        ngrams = service.top_ngrams(
            [
                "What I am looking for is more of the Twinkl resources in the classroom",
                "I am using Twinkl in the classroom and of the resources",
            ],
            ngram_size=1,
            top_n=10,
        )

        self.assertEqual([item["term"] for item in ngrams], ["twinkl", "resources", "classroom"])

    def test_top_terms_drop_two_letter_tokens_during_label_cleanup(self) -> None:
        service = TopicAnalysisKeywordService()

        terms = service.top_terms(
            [
                "AI support in UK schools",
                "UK support for AI in class",
            ],
            top_n=10,
        )

        self.assertEqual(terms, ["support", "schools", "class"])

    def test_top_terms_remove_spanish_function_words(self) -> None:
        service = TopicAnalysisKeywordService()

        terms = service.top_terms(
            [
                "para los que las recursos busqueda organizacion recursos",
                "los recursos para organizacion y busqueda",
            ],
            top_n=10,
        )

        self.assertEqual(terms, ["recursos", "busqueda", "organizacion"])

    def test_label_fallback_does_not_use_stopword_only_terms(self) -> None:
        keyword_service = TopicAnalysisKeywordService()
        narrative_service = TopicAnalysisNarrativeService(keyword_service)

        label = narrative_service.build_label(
            texts=[],
            terms=["para", "los", "que las"],
            is_noise=False,
            fallback_prefix="Group",
            fallback_id="7",
            prefer_terms=True,
        )

        self.assertEqual(label, "Group 7")


class CommunityDetectionAnalysisServiceTests(unittest.TestCase):
    def test_run_uses_leiden_when_available(self) -> None:
        class _FakeEdgeSequence:
            def __init__(self, graph) -> None:
                self.graph = graph

            def __setitem__(self, key, value) -> None:
                if key == "weight":
                    self.graph.weights = list(value)

        class _FakeGraph:
            last_instance = None

            def __init__(self) -> None:
                type(self).last_instance = self
                self.vertex_count = 0
                self.edges: list[tuple[int, int]] = []
                self.weights: list[float] = []
                self.es = _FakeEdgeSequence(self)

            def add_vertices(self, count: int) -> None:
                self.vertex_count = int(count)

            def add_edges(self, edges) -> None:
                self.edges = list(edges)

        class _FakePartition:
            membership = [0, 0, 1, 1]

        calls: list[dict[str, object]] = []

        def find_partition(graph, partition_type, **kwargs):
            calls.append(
                {
                    "graph": graph,
                    "partition_type": partition_type,
                    **kwargs,
                }
            )
            return _FakePartition()

        fake_igraph = types.ModuleType("igraph")
        fake_igraph.Graph = _FakeGraph
        fake_leidenalg = types.ModuleType("leidenalg")
        fake_leidenalg.RBConfigurationVertexPartition = object()
        fake_leidenalg.find_partition = find_partition
        service = CommunityDetectionAnalysisService()

        with patch.dict(sys.modules, {"igraph": fake_igraph, "leidenalg": fake_leidenalg}):
            result = service.run(
                [
                    [1.0, 0.0],
                    [0.99, 0.01],
                    [-1.0, 0.0],
                    [-0.99, -0.01],
                ],
                similarity_threshold=0.8,
                max_neighbors=2,
                resolution=1.35,
            )

        self.assertEqual(result.assignments, [0, 0, 1, 1])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["weights"], "weight")
        self.assertEqual(calls[0]["resolution_parameter"], 1.35)
        self.assertEqual(calls[0]["seed"], 42)
        self.assertEqual(_FakeGraph.last_instance.vertex_count, 4)
        self.assertTrue(_FakeGraph.last_instance.edges)
        self.assertTrue(_FakeGraph.last_instance.weights)
        self.assertNotIn("greedy modularity", " ".join(result.warnings))

    def test_run_groups_similar_embedding_neighborhoods_into_communities(self) -> None:
        service = CommunityDetectionAnalysisService()

        result = service.run(
            [
                [1.0, 0.0],
                [0.99, 0.01],
                [-1.0, 0.0],
                [-0.99, -0.01],
            ],
            similarity_threshold=0.8,
            max_neighbors=2,
        )

        self.assertEqual(len(result.assignments), 4)
        self.assertEqual(result.assignments[0], result.assignments[1])
        self.assertEqual(result.assignments[2], result.assignments[3])
        self.assertNotEqual(result.assignments[0], result.assignments[2])
        self.assertEqual(set(result.layout_positions.keys()), {0, 1, 2, 3})
        self.assertTrue(result.network_edges)

    def test_run_requires_mutual_neighbors_by_default(self) -> None:
        service = CommunityDetectionAnalysisService()
        embeddings = [
            [1.0, 0.0],
            [0.9, 0.4358898944],
            [0.8, 0.6],
        ]

        strict_result = service.run(
            embeddings,
            similarity_threshold=0.75,
            max_neighbors=1,
        )
        loose_result = service.run(
            embeddings,
            similarity_threshold=0.75,
            max_neighbors=1,
            mutual_neighbors=False,
        )

        strict_edges = {(source, target) for source, target, _weight in strict_result.network_edges}
        loose_edges = {(source, target) for source, target, _weight in loose_result.network_edges}
        self.assertEqual(strict_edges, {(1, 2)})
        self.assertEqual(loose_edges, {(0, 1), (1, 2)})

    def test_run_applies_stricter_same_language_threshold_for_non_english_edges(self) -> None:
        service = CommunityDetectionAnalysisService()
        embeddings = [
            [1.0, 0.0],
            [0.75, 0.6614378278],
        ]

        unguarded_result = service.run(
            embeddings,
            similarity_threshold=0.7,
            max_neighbors=1,
            mutual_neighbors=False,
        )
        guarded_result = service.run(
            embeddings,
            similarity_threshold=0.7,
            max_neighbors=1,
            mutual_neighbors=False,
            languages=["es", "es"],
        )

        self.assertEqual(len(unguarded_result.network_edges), 1)
        self.assertEqual(guarded_result.network_edges, [])
        self.assertIn("stricter same-language", " ".join(guarded_result.warnings))

    def test_run_splits_language_dominant_communities_with_weak_topical_links(self) -> None:
        class _FakeEdgeSequence:
            def __init__(self, graph) -> None:
                self.graph = graph

            def __setitem__(self, key, value) -> None:
                if key == "weight":
                    self.graph.weights = list(value)

        class _FakeGraph:
            def __init__(self) -> None:
                self.vertex_count = 0
                self.edges: list[tuple[int, int]] = []
                self.weights: list[float] = []
                self.es = _FakeEdgeSequence(self)

            def add_vertices(self, count: int) -> None:
                self.vertex_count = int(count)

            def add_edges(self, edges) -> None:
                self.edges = list(edges)

        class _FakePartition:
            membership = [0, 0, 0, 0]

        def find_partition(graph, partition_type, **kwargs):
            return _FakePartition()

        fake_igraph = types.ModuleType("igraph")
        fake_igraph.Graph = _FakeGraph
        fake_leidenalg = types.ModuleType("leidenalg")
        fake_leidenalg.RBConfigurationVertexPartition = object()
        fake_leidenalg.find_partition = find_partition

        service = CommunityDetectionAnalysisService()
        with patch.dict(sys.modules, {"igraph": fake_igraph, "leidenalg": fake_leidenalg}):
            result = service.run(
                [
                    [1.0, 0.0],
                    [0.9, 0.4358898944],
                    [-1.0, 0.0],
                    [-0.9, -0.4358898944],
                ],
                similarity_threshold=0.7,
                max_neighbors=2,
                mutual_neighbors=False,
                languages=["es", "es", "es", "es"],
            )

        self.assertEqual(result.assignments, [0, 0, 1, 1])
        self.assertIn("split 1 language-dominant community", " ".join(result.warnings))

    def test_run_marks_all_responses_as_noise_when_no_edges_match_threshold(self) -> None:
        service = CommunityDetectionAnalysisService()

        result = service.run(
            [
                [1.0, 0.0],
                [0.0, 1.0],
                [-1.0, 0.0],
            ],
            similarity_threshold=0.99,
            max_neighbors=2,
        )

        self.assertEqual(result.assignments, [-1, -1, -1])
        self.assertTrue(result.groups["-1"].is_noise)
        self.assertIn("all responses were marked as unassigned noise", " ".join(result.warnings))

    def test_run_marks_singleton_communities_as_noise(self) -> None:
        service = CommunityDetectionAnalysisService()

        result = service.run(
            [
                [1.0, 0.0],
                [0.99, 0.01],
                [0.0, 1.0],
            ],
            similarity_threshold=0.8,
            max_neighbors=2,
        )

        self.assertEqual(result.assignments, [0, 0, -1])
        self.assertTrue(result.groups["-1"].is_noise)
        self.assertIn("marked 1 weakly connected response", " ".join(result.warnings))

    def test_run_marks_tiny_communities_as_noise_when_sample_is_large_enough(self) -> None:
        service = CommunityDetectionAnalysisService()

        result = service.run(
            [
                [1.0, 0.0],
                [0.99, 0.01],
                [-1.0, 0.0],
                [-0.99, -0.01],
                [-0.98, -0.02],
            ],
            similarity_threshold=0.8,
            max_neighbors=3,
        )

        self.assertEqual(result.assignments, [-1, -1, 0, 0, 0])
        self.assertTrue(result.groups["-1"].is_noise)
        self.assertIn("marked 2 weakly connected response", " ".join(result.warnings))

    def test_run_falls_back_to_raw_embeddings_when_umap_reduction_fails(self) -> None:
        class _FailingReducer:
            def __init__(self, **kwargs) -> None:
                pass

            def fit_transform(self, embeddings):
                raise TypeError("check_array() got an unexpected keyword argument 'force_all_finite'")

        fake_umap = types.ModuleType("umap")
        fake_umap.UMAP = _FailingReducer
        service = CommunityDetectionAnalysisService()
        embeddings = [[1.0, *([0.0] * 15)] for _index in range(10)]

        with (
            patch.object(CommunityDetectionAnalysisService, "_has_incompatible_umap_runtime", return_value=False),
            patch.dict(sys.modules, {"umap": fake_umap}),
        ):
            result = service.run(
                embeddings,
                similarity_threshold=0.8,
                max_neighbors=3,
            )

        self.assertEqual(len(result.assignments), 10)
        self.assertIn("UMAP clustering reduction was skipped", " ".join(result.warnings))

    def test_run_reuses_umap_clustering_projection_for_layout(self) -> None:
        class _CountingReducer:
            fit_calls = 0

            def __init__(self, **kwargs) -> None:
                self.n_components = int(kwargs["n_components"])

            def fit_transform(self, embeddings):
                type(self).fit_calls += 1
                return [
                    [float(row_index + component_index) for component_index in range(self.n_components)]
                    for row_index, _embedding in enumerate(embeddings)
                ]

        fake_umap = types.ModuleType("umap")
        fake_umap.UMAP = _CountingReducer
        service = CommunityDetectionAnalysisService()
        embeddings = [[float(index), *([0.0] * 15)] for index in range(10)]

        with (
            patch.object(CommunityDetectionAnalysisService, "_has_incompatible_umap_runtime", return_value=False),
            patch.dict(sys.modules, {"umap": fake_umap}),
        ):
            result = service.run(
                embeddings,
                similarity_threshold=0.99,
                max_neighbors=3,
            )

        self.assertEqual(_CountingReducer.fit_calls, 1)
        self.assertEqual(result.layout_positions[0], (0.0, 1.0))

    def test_normalize_languages_pads_and_ignores_auto_values(self) -> None:
        normalized = CommunityDetectionAnalysisService._normalize_languages(
            [" EN ", "auto", "ES"],
            document_count=5,
        )

        self.assertEqual(normalized, ["en", None, "es", None, None])


class SentenceEmbeddingServiceTests(unittest.TestCase):
    def test_warm_up_is_noop_for_hosted_embedding_providers(self) -> None:
        service = SentenceEmbeddingService()

        with patch("requests.post") as post:
            service.warm_up(provider="gemini", model_name="gemini-embedding-001")

        post.assert_not_called()

    def test_encode_uses_gemini_batch_embeddings_and_normalises_vectors(self) -> None:
        calls = []

        def fake_post(*args, **kwargs):
            calls.append({"args": args, "kwargs": kwargs})
            return _FakeEmbeddingResponse(
                {
                    "embeddings": [
                        {"values": [3.0, 4.0]},
                        {"values": [0.0, 5.0]},
                    ]
                }
            )

        service = SentenceEmbeddingService()
        with patch("requests.post", side_effect=fake_post):
            embeddings = service.encode(
                ["first", "second"],
                provider="gemini",
                model_name="gemini-embedding-001",
                api_key="test-key",
                dimensions=2,
                batch_size=2,
                timeout_seconds=9,
            )

        self.assertEqual(len(calls), 1)
        self.assertEqual(
            calls[0]["args"][0],
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:batchEmbedContents",
        )
        self.assertEqual(calls[0]["kwargs"]["headers"]["x-goog-api-key"], "test-key")
        self.assertEqual(calls[0]["kwargs"]["timeout"], 9)
        request_payload = calls[0]["kwargs"]["json"]["requests"][0]
        self.assertEqual(request_payload["taskType"], "CLUSTERING")
        self.assertEqual(request_payload["outputDimensionality"], 2)
        self.assertAlmostEqual(float(embeddings[0][0]), 0.6)
        self.assertAlmostEqual(float(embeddings[0][1]), 0.8)
        self.assertAlmostEqual(float(embeddings[1][1]), 1.0)
        self.assertEqual(embeddings.dtype.name, "float32")

    def test_encode_uses_openai_embeddings_and_preserves_response_order(self) -> None:
        def fake_post(*args, **kwargs):
            return _FakeEmbeddingResponse(
                {
                    "data": [
                        {"index": 1, "embedding": [0.0, 6.0]},
                        {"index": 0, "embedding": [8.0, 6.0]},
                    ]
                }
            )

        service = SentenceEmbeddingService()
        with patch("requests.post", side_effect=fake_post) as post:
            embeddings = service.encode(
                ["first", "second"],
                provider="openai",
                model_name="text-embedding-3-small",
                api_key="test-key",
                dimensions=2,
                batch_size=128,
                timeout_seconds=11,
            )

        call = post.call_args
        self.assertEqual(call.args[0], "https://api.openai.com/v1/embeddings")
        self.assertEqual(call.kwargs["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(call.kwargs["json"]["dimensions"], 2)
        self.assertEqual(call.kwargs["timeout"], 11)
        self.assertAlmostEqual(float(embeddings[0][0]), 0.8)
        self.assertAlmostEqual(float(embeddings[0][1]), 0.6)
        self.assertAlmostEqual(float(embeddings[1][1]), 1.0)

    def test_encode_batches_openai_requests_at_128_by_default(self) -> None:
        calls: list[list[str]] = []

        def fake_post(*args, **kwargs):
            batch = list(kwargs["json"]["input"])
            calls.append(batch)
            return _FakeEmbeddingResponse(
                {
                    "data": [
                        {"index": index, "embedding": [1.0, 0.0]}
                        for index, _text in enumerate(batch)
                    ]
                }
            )

        service = SentenceEmbeddingService()
        with patch("requests.post", side_effect=fake_post):
            embeddings = service.encode(
                [f"text {index}" for index in range(129)],
                provider="openai",
                model_name="text-embedding-3-small",
                api_key="test-key",
            )

        self.assertEqual([len(batch) for batch in calls], [128, 1])
        self.assertEqual(embeddings.shape[0], 129)

    def test_encode_caps_gemini_batches_at_provider_limit(self) -> None:
        calls: list[list[dict[str, object]]] = []

        def fake_post(*args, **kwargs):
            batch = list(kwargs["json"]["requests"])
            calls.append(batch)
            return _FakeEmbeddingResponse(
                {
                    "embeddings": [
                        {"values": [1.0, 0.0]}
                        for _request in batch
                    ]
                }
            )

        service = SentenceEmbeddingService()
        with patch("requests.post", side_effect=fake_post):
            embeddings = service.encode(
                [f"text {index}" for index in range(128)],
                provider="gemini",
                model_name="gemini-embedding-001",
                api_key="test-key",
                batch_size=128,
            )

        self.assertEqual([len(batch) for batch in calls], [100, 28])
        self.assertEqual(embeddings.shape[0], 128)

    def test_encode_retries_retryable_provider_errors(self) -> None:
        responses = [
            _FakeEmbeddingResponse({"error": {"message": "Temporary outage."}}, status_code=503),
            _FakeEmbeddingResponse({"embeddings": [{"values": [1.0, 0.0]}]}),
        ]

        def fake_post(*args, **kwargs):
            return responses.pop(0)

        service = SentenceEmbeddingService(cache_size=0, max_retries=1, retry_base_seconds=0)
        with patch("requests.post", side_effect=fake_post) as post:
            embeddings = service.encode(
                ["first"],
                provider="gemini",
                model_name="gemini-embedding-001",
                api_key="test-key",
            )

        self.assertEqual(post.call_count, 2)
        self.assertEqual(embeddings.shape[0], 1)

    def test_provider_retry_delay_reads_nested_retry_info_payload(self) -> None:
        service = SentenceEmbeddingService(cache_size=0, max_retries=0)
        response = _FakeEmbeddingResponse(
            {
                "error": {
                    "message": "Resource exhausted.",
                    "details": [
                        {
                            "@type": "type.googleapis.com/google.rpc.RetryInfo",
                            "retryDelay": "3.5s",
                        }
                    ],
                }
            },
            status_code=429,
        )

        self.assertEqual(service._provider_retry_delay_seconds(response), 3.5)

    def test_gemini_rate_limit_error_is_retryable_by_the_caller(self) -> None:
        service = SentenceEmbeddingService(cache_size=0, max_retries=0)
        with patch(
            "requests.post",
            return_value=_FakeEmbeddingResponse({"error": {"message": "Resource exhausted."}}, status_code=429),
        ):
            with self.assertRaises(TopicAnalysisRateLimitError) as context:
                service.encode(
                    ["first"],
                    provider="gemini",
                    model_name="gemini-embedding-001",
                    api_key="test-key",
                )

        self.assertEqual(str(context.exception), "Gemini is rate limited. Try again later.")
        self.assertEqual(context.exception.error_code, "gemini_rate_limited")
        self.assertEqual(context.exception.retry_after_seconds, 60)

    def test_gemini_daily_quota_error_does_not_claim_two_minute_recovery(self) -> None:
        service = SentenceEmbeddingService(cache_size=0, max_retries=0)
        response_payload = {
            "error": {
                "message": "Quota exceeded for daily embedding requests.",
                "status": "RESOURCE_EXHAUSTED",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                        "violations": [
                            {
                                "quotaId": "BatchEmbedContentsRequestsPerDayPerProjectPerModel-FreeTier",
                                "quotaMetric": "generativelanguage.googleapis.com/batch_embed_contents_free_tier_requests",
                            }
                        ],
                    }
                ],
            }
        }
        with patch("requests.post", return_value=_FakeEmbeddingResponse(response_payload, status_code=429)):
            with self.assertRaises(TopicAnalysisDependencyError) as context:
                service.encode(
                    ["first"],
                    provider="gemini",
                    model_name="gemini-embedding-001",
                    api_key="test-key",
                )

        self.assertEqual(
            str(context.exception),
            "Gemini quota is exhausted for today. Try again after the daily quota resets.",
        )

    def test_encode_caches_duplicate_texts_and_reuses_cached_vectors(self) -> None:
        calls: list[list[dict[str, object]]] = []

        def fake_post(*args, **kwargs):
            batch = list(kwargs["json"]["requests"])
            calls.append(batch)
            return _FakeEmbeddingResponse(
                {
                    "embeddings": [
                        {"values": [1.0, 0.0]}
                        for _request in batch
                    ]
                }
            )

        service = SentenceEmbeddingService(cache_size=10, max_retries=0)
        with patch("requests.post", side_effect=fake_post):
            first_embeddings = service.encode(
                ["same text", "same text"],
                provider="gemini",
                model_name="gemini-embedding-001",
                api_key="test-key",
            )
            second_embeddings = service.encode(
                ["same text"],
                provider="gemini",
                model_name="gemini-embedding-001",
                api_key="test-key",
            )

        self.assertEqual([len(batch) for batch in calls], [1])
        self.assertEqual(first_embeddings.shape[0], 2)
        self.assertEqual(second_embeddings.shape[0], 1)
        cached_vector = next(iter(service._cache.values()))
        self.assertEqual(cached_vector.dtype.name, "float32")
        self.assertFalse(cached_vector.flags.writeable)

    def test_model_execution_uses_fallback_embeddings_when_primary_provider_fails(self) -> None:
        _FakeFallbackEmbeddingService.calls = []
        config = TopicAnalysisConfig(
            embedding_provider="gemini",
            embedding_model="gemini-embedding-001",
            embedding_api_key="gemini-key",
            embedding_dimensions=768,
            embedding_batch_size=128,
            embedding_timeout_seconds=60,
            community_similarity_threshold=0.62,
            community_max_neighbors=12,
            top_terms_per_group=5,
            top_ngrams_per_bucket=6,
            representative_examples_per_group=2,
            max_document_chars=300,
            embedding_fallback_provider="openai",
            embedding_fallback_model="text-embedding-3-small",
            embedding_fallback_api_key="openai-key",
        )
        service = TopicModelExecutionService(
            config=config,
            embedding_service=_FakeFallbackEmbeddingService(),
            community_detection_service=_EmbeddingPassthroughCommunityService(),
        )

        execution = service.execute(
            model_key=AnalysisModelKey.COMMUNITY,
            texts=["first", "second"],
        )

        self.assertEqual(_FakeFallbackEmbeddingService.calls, ["gemini", "openai"])
        self.assertEqual(execution.result.assignments, [0, 0])
        self.assertIn("OpenAI embeddings were used", " ".join(execution.warnings or []))


class TopicAnalysisServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        _FakeEmbeddingService.last_texts = []
        keyword_service = TopicAnalysisKeywordService()
        self.config = TopicAnalysisConfig(
            embedding_provider="gemini",
            embedding_model="gemini-embedding-001",
            embedding_api_key="test-key",
            embedding_dimensions=768,
            embedding_batch_size=128,
            embedding_timeout_seconds=60,
            community_similarity_threshold=0.62,
            community_max_neighbors=12,
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

    def _build_service(
        self,
        *,
        text_preparation_service: TopicAnalysisTextPreparationService | None = None,
        embedding_service=None,
        community_detection_service=None,
        ai_label_service=None,
    ) -> TopicAnalysisService:
        return TopicAnalysisService(
            config=self.config,
            input_validation_service=self.validation_service,
            text_preparation_service=text_preparation_service or self.text_preparation_service,
            keyword_service=self.keyword_service,
            narrative_service=self.narrative_service,
            representative_example_service=self.example_service,
            embedding_service=embedding_service or _FakeEmbeddingService(),
            ngram_service=self.ngram_service,
            community_detection_service=community_detection_service or _UnusedService(),
            ai_label_service=ai_label_service,
        )

    def test_run_ngrams_translates_output_terms_only(self) -> None:
        service = self._build_service(
            text_preparation_service=TopicAnalysisTextPreparationService(
                max_document_chars=300,
                translation_service=_FakeEnglishTranslationService(
                    {
                        "necesito": "need",
                        "recursos": "resources",
                        "matematicas": "maths",
                    }
                ),
            )
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
            model_key=AnalysisModelKey.NGRAMS,
            text_column_name="verbatim",
            available_verbatim_columns=["verbatim"],
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.valid_document_count, 2)
        self.assertEqual(result.skipped_document_count, 1)
        self.assertGreaterEqual(result.translated_document_count, 1)
        self.assertIsNone(result.error)
        self.assertEqual(len(result.ngram_buckets), 3)
        self.assertEqual(result.ngram_buckets[0].label, "Single Words")
        self.assertGreaterEqual(len(result.ngram_buckets[0].items), 1)
        self.assertTrue(any(item.translated for item in result.ngram_buckets[0].items))
        self.assertIn("Translated", " ".join(result.warnings))

    def test_run_returns_retry_metadata_for_gemini_rate_limits(self) -> None:
        service = self._build_service(
            embedding_service=_FakeRateLimitedEmbeddingService(),
            community_detection_service=_UnusedService(),
        )
        dataframe = pd.DataFrame(
            {
                "verbatim": [
                    "Need more maths worksheets",
                    "Need clearer instructions",
                ],
            }
        )

        result = service.run(
            result_id="abc123",
            dataframe=dataframe,
            model_key=AnalysisModelKey.COMMUNITY,
            text_column_name="verbatim",
            available_verbatim_columns=["verbatim"],
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error, "Gemini is rate limited. Try again later.")
        self.assertEqual(result.error_code, "gemini_rate_limited")
        self.assertEqual(result.retry_after_seconds, 60)

    def test_run_ngrams_keeps_translated_display_terms_stopword_free(self) -> None:
        service = self._build_service(
            text_preparation_service=TopicAnalysisTextPreparationService(
                max_document_chars=300,
                translation_service=_FakeEnglishTranslationService(
                    {
                        "mi aula": "in the classroom",
                    }
                ),
            )
        )
        dataframe = pd.DataFrame(
            {
                "verbatim": [
                    "mi aula",
                    "mi aula",
                    "mi aula",
                ],
            }
        )

        result = service.run(
            result_id="abc123",
            dataframe=dataframe,
            model_key=AnalysisModelKey.NGRAMS,
            text_column_name="verbatim",
            available_verbatim_columns=["verbatim"],
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.ngram_buckets[0].items[0].term, "classroom")

    def test_run_ngrams_includes_matching_documents_for_each_item(self) -> None:
        service = self._build_service()
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
            model_key=AnalysisModelKey.NGRAMS,
            text_column_name="verbatim",
            available_verbatim_columns=["verbatim"],
        )

        bigram_items = result.ngram_buckets[1].items
        matching_item = next(item for item in bigram_items if item.term == "science resources")
        self.assertEqual(matching_item.count, 2)
        self.assertEqual(matching_item.document_count, 2)
        self.assertEqual(
            [{"row_number": d.row_number, "text": d.text} for d in matching_item.documents],
            [
                {"row_number": 1, "text": "Need more science resources"},
                {"row_number": 2, "text": "More science resources help"},
            ],
        )

    def test_run_community_translates_group_outputs_after_grouping(self) -> None:
        service = self._build_service(
            text_preparation_service=TopicAnalysisTextPreparationService(
                max_document_chars=300,
                translation_service=_FakeEnglishTranslationService(
                    {
                        "Responses about ayuda docente": "Responses about teaching support",
                        "ayuda docente": "teaching support",
                    }
                ),
            ),
            community_detection_service=_FakeCommunityDetectionService(),
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
            model_key=AnalysisModelKey.COMMUNITY,
            text_column_name="verbatim",
            available_verbatim_columns=["verbatim"],
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.model_label, "Community Detection")
        self.assertEqual(len(result.groups), 2)
        self.assertEqual(result.groups[0].count, 2)
        # Label is built from translated English texts — already English, no output translation needed
        self.assertIn("teaching support", result.groups[0].label.casefold())
        self.assertIsNone(result.groups[0].source_label)
        self.assertFalse(result.groups[0].translated)
        self.assertGreaterEqual(len(result.groups[0].examples), 1)
        # Examples are translated at input time — source_text preserved, translated flag set
        self.assertTrue(result.groups[0].examples[0].translated)
        self.assertEqual(result.groups[0].examples[0].source_text, "ayuda docente")
        self.assertEqual(result.groups[0].examples[0].text, "teaching support")
        self.assertIn("Representative document", result.groups[0].comment)
        self.assertIn("Community detection test warning.", result.warnings)
        # translated_document_count now reflects input-time translation (2 docs)
        self.assertGreaterEqual(result.translated_document_count, 2)
        self.assertEqual(len(result.scatter_points), 3)
        self.assertEqual(len(result.network_edges), 1)
        self.assertEqual(result.network_edges[0].source_row_number, 1)
        self.assertEqual(result.network_edges[0].target_row_number, 2)

    def test_run_community_plot_links_sentence_fragments_to_full_source_response(self) -> None:
        service = self._build_service(community_detection_service=_FakeCommunityDetectionService())
        full_response = "Need clearer curriculum labels. More examples would help teachers."
        dataframe = pd.DataFrame(
            {
                "verbatim": [
                    full_response,
                    "Better search filters would help",
                ]
            }
        )

        result = service.run(
            result_id="abc123",
            dataframe=dataframe,
            model_key=AnalysisModelKey.COMMUNITY,
            text_column_name="verbatim",
            available_verbatim_columns=["verbatim"],
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.original_response_count, 2)
        self.assertEqual(result.valid_document_count, 3)
        self.assertEqual(len(result.scatter_points), 3)
        self.assertEqual(result.scatter_points[0].text, "Need clearer curriculum labels.")
        self.assertEqual(result.scatter_points[1].text, "More examples would help teachers.")
        self.assertEqual(result.scatter_points[0].source_text, full_response)
        self.assertEqual(result.scatter_points[1].source_text, full_response)
        self.assertEqual(result.scatter_points[0].point_index, 0)
        self.assertEqual(result.scatter_points[1].point_index, 1)
        self.assertEqual(result.network_edges[0].source_point_index, 0)
        self.assertEqual(result.network_edges[0].target_point_index, 1)

    def test_run_community_can_replace_heuristic_labels_with_ai_labels_without_retranslating_them(self) -> None:
        translation_service = _FakeEnglishTranslationService(
            {
                "ayuda docente": "teaching support",
            }
        )
        service = self._build_service(
            text_preparation_service=TopicAnalysisTextPreparationService(
                max_document_chars=300,
                translation_service=translation_service,
            ),
            community_detection_service=_FakeCommunityDetectionService(),
            ai_label_service=_FakeAiLabelService({"0": "Teaching Support Feedback"}),
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
            model_key=AnalysisModelKey.COMMUNITY,
            text_column_name="verbatim",
            available_verbatim_columns=["verbatim"],
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.groups[0].label, "Teaching Support Feedback")
        # source_label is the English heuristic label built from input-translated texts
        self.assertIsNotNone(result.groups[0].source_label)
        self.assertIn("teaching support", result.groups[0].source_label.casefold())
        self.assertTrue(result.groups[0].ai_generated)
        self.assertFalse(result.groups[0].translated)
        self.assertTrue(all("Teaching Support Feedback" not in batch for batch in translation_service.calls))
        self.assertIn("AI generated clearer labels", " ".join(result.warnings))

    def test_run_embeds_original_cleaned_text_but_keeps_filtered_topic_terms(self) -> None:
        service = self._build_service(community_detection_service=_FakeCommunityDetectionService())
        dataframe = pd.DataFrame(
            {
                "verbatim": [
                    "What I need is more support in the classroom",
                    "Need more maths challenge activities",
                    "What I need is support in class",
                ]
            }
        )

        result = service.run(
            result_id="abc123",
            dataframe=dataframe,
            model_key=AnalysisModelKey.COMMUNITY,
            text_column_name="verbatim",
            available_verbatim_columns=["verbatim"],
        )

        self.assertTrue(result.ok)
        self.assertEqual(
            _FakeEmbeddingService.last_texts,
            [
                "What I need is more support in the classroom",
                "Need more maths challenge activities",
                "What I need is support in class",
            ],
        )
        self.assertIn(
            result.groups[0].examples[0].text,
            {
                "What I need is more support in the classroom",
                "Need more maths challenge activities",
            },
        )

    def test_run_community_orders_group_documents_by_top_term_evidence(self) -> None:
        service = self._build_service(community_detection_service=_SingleCommunityDetectionService())
        dataframe = pd.DataFrame(
            {
                "verbatim": [
                    "General feedback about the platform",
                    "Need more science resources and maths resources",
                    "Resources should include lesson plans and classroom materials",
                    "The login screen is confusing",
                ]
            }
        )

        result = service.run(
            result_id="abc123",
            dataframe=dataframe,
            model_key=AnalysisModelKey.COMMUNITY,
            text_column_name="verbatim",
            available_verbatim_columns=["verbatim"],
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.groups[0].terms[0], "resources")
        self.assertEqual(
            [document.row_number for document in result.groups[0].documents[:2]],
            [2, 3],
        )

    def test_run_community_orders_group_documents_by_graph_representativeness_before_terms(self) -> None:
        service = self._build_service(community_detection_service=_CentralCommunityDetectionService())
        dataframe = pd.DataFrame(
            {
                "verbatim": [
                    "Resources resources resources are available",
                    "Need better lesson planning support",
                    "Need clearer lesson planning support",
                    "Need better planning resources",
                ]
            }
        )

        result = service.run(
            result_id="abc123",
            dataframe=dataframe,
            model_key=AnalysisModelKey.COMMUNITY,
            text_column_name="verbatim",
            available_verbatim_columns=["verbatim"],
        )

        self.assertTrue(result.ok)
        self.assertEqual(
            [document.row_number for document in result.groups[0].documents],
            [3, 2, 4, 1],
        )

    def test_run_community_merges_groups_with_duplicate_ai_labels(self) -> None:
        service = self._build_service(
            community_detection_service=_DuplicateLabelCommunityDetectionService(),
            ai_label_service=_FakeAiLabelService({"0": "Search And Curriculum Issues", "1": "Search And Curriculum Issues"}),
        )
        dataframe = pd.DataFrame(
            {
                "verbatim": [
                    "Need clearer search filters",
                    "Search filters are confusing",
                    "Need better curriculum links",
                    "Curriculum links are hard to find",
                ]
            }
        )

        result = service.run(
            result_id="abc123",
            dataframe=dataframe,
            model_key=AnalysisModelKey.COMMUNITY,
            text_column_name="verbatim",
            available_verbatim_columns=["verbatim"],
        )

        self.assertTrue(result.ok)
        self.assertEqual(len(result.groups), 1)
        self.assertEqual(result.groups[0].label, "Search And Curriculum Issues")
        self.assertEqual(result.groups[0].count, 4)
        self.assertEqual([document.row_number for document in result.groups[0].documents], [1, 2, 4, 3])
        self.assertEqual({point.group_id for point in result.scatter_points}, {"0"})
        self.assertEqual({point.group_label for point in result.scatter_points}, {"Search And Curriculum Issues"})

    def test_run_keeps_heuristic_labels_when_ai_labeling_fails(self) -> None:
        service = self._build_service(
            community_detection_service=_FakeCommunityDetectionService(),
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
            model_key=AnalysisModelKey.COMMUNITY,
            text_column_name="verbatim",
            available_verbatim_columns=["verbatim"],
        )

        self.assertTrue(result.ok)
        self.assertFalse(result.groups[0].ai_generated)
        self.assertEqual(result.groups[0].label, "Classroom Materials")
        self.assertNotIn("Requests for", result.groups[0].label)
        self.assertIn("AI topic labeling was skipped", " ".join(result.warnings))

    def test_invalid_column_returns_structured_error_response(self) -> None:
        service = self._build_service(
            embedding_service=SentenceEmbeddingService(),
            community_detection_service=CommunityDetectionAnalysisService(),
        )
        dataframe = pd.DataFrame({"verbatim": ["Need more resources"]})

        result = service.run(
            result_id="abc123",
            dataframe=dataframe,
            model_key=AnalysisModelKey.NGRAMS,
            text_column_name="wrong_column",
            available_verbatim_columns=["verbatim"],
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.valid_document_count, 0)
        self.assertIn("Choose one of the detected verbatim columns", result.error)


if __name__ == "__main__":
    unittest.main()
