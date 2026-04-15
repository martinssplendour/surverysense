from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import logging
import math
import re
from threading import Lock
from typing import Any, Iterable

import pandas as pd

from app.core.exceptions import (
    TopicAnalysisDependencyError,
    TopicAnalysisInputError,
)
from app.services.language_normalization_service import EnglishTranslationService
from app.services.topic_label_ai_service import TopicAiLabelService


MODEL_LABELS = {
    "bertopic": "AI Themes",
    "kmeans": "Response Groups",
    "hdbscan": "Natural Groups",
    "ngrams": "Common Phrases",
}

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TopicAnalysisConfig:
    embedding_model: str
    kmeans_clusters: int
    kmeans_random_state: int
    hdbscan_min_cluster_size: int
    hdbscan_min_samples: int
    hdbscan_metric: str
    bertopic_language: str
    bertopic_reduce_outliers: bool
    bertopic_outlier_threshold: float
    top_terms_per_group: int
    top_ngrams_per_bucket: int
    representative_examples_per_group: int
    max_document_chars: int


@dataclass(slots=True)
class PreparedDocument:
    row_number: int
    text: str
    source_text: str
    translated_to_english: bool = False
    detected_language: str | None = None


@dataclass(slots=True)
class PreparedTextDataset:
    documents: list[PreparedDocument]
    total_row_count: int
    skipped_row_count: int
    translated_document_count: int
    warnings: list[str]

    @property
    def texts(self) -> list[str]:
        return [document.text for document in self.documents]

    @property
    def unique_document_count(self) -> int:
        return len({document.text.casefold() for document in self.documents})


class TopicAnalysisInputValidationService:
    SUPPORTED_MODELS = frozenset(MODEL_LABELS)

    def get_model_label(self, model_key: str) -> str:
        return MODEL_LABELS.get(model_key, model_key.upper())

    def validate_request(
        self,
        *,
        model_key: str,
        text_column_name: str,
        available_verbatim_columns: Iterable[str],
    ) -> None:
        if model_key not in self.SUPPORTED_MODELS:
            raise TopicAnalysisInputError(f"Unsupported analysis mode '{model_key}'.")

        verbatim_column_set = set(available_verbatim_columns)
        if text_column_name not in verbatim_column_set:
            raise TopicAnalysisInputError(
                "Choose one of the detected verbatim columns before running analysis."
            )

    def validate_dataset(self, prepared: PreparedTextDataset, *, model_key: str) -> list[str]:
        warnings = list(prepared.warnings)
        valid_count = len(prepared.documents)
        if valid_count == 0:
            raise TopicAnalysisInputError(
                "The selected column does not contain any usable text after removing empty and NaN values."
            )

        if model_key != "ngrams":
            if valid_count < 2:
                raise TopicAnalysisInputError(
                    "This analysis mode needs at least two non-empty responses."
                )
            if prepared.unique_document_count < 2:
                raise TopicAnalysisInputError(
                    "This analysis mode needs at least two unique responses after cleaning."
                )

        if model_key == "hdbscan" and valid_count < 5:
            warnings.append(
                "Natural Groups works best with at least 5 usable responses. Smaller samples may not form clear groups."
            )
        if model_key == "bertopic" and valid_count < 5:
            warnings.append(
                "AI Themes works best with a larger sample. Smaller samples can produce unstable themes."
            )
        if model_key == "kmeans" and valid_count < 5:
            warnings.append(
                "Response Groups is running on a small sample, so the groups may be weak."
            )
        return warnings


class TopicAnalysisTextPreparationService:
    PLACEHOLDER_VALUES = frozenset(
        {
            "",
            "na",
            "n/a",
            "nan",
            "none",
            "null",
            "nil",
            "-",
            "--",
        }
    )
    WHITESPACE_PATTERN = re.compile(r"\s+")

    def __init__(
        self,
        *,
        max_document_chars: int,
        translation_service: EnglishTranslationService | None = None,
    ) -> None:
        self.max_document_chars = max(200, max_document_chars)
        self.translation_service = translation_service

    def warm_up(self) -> None:
        if self.translation_service is not None:
            self.translation_service.warm_up()

    def prepare(self, dataframe: pd.DataFrame, *, text_column_name: str) -> PreparedTextDataset:
        if text_column_name not in dataframe.columns:
            raise TopicAnalysisInputError(f"Column '{text_column_name}' is not available in the analysis dataset.")

        documents: list[PreparedDocument] = []
        warnings: list[str] = []
        skipped_count = 0
        truncated_count = 0

        for row_index, raw_value in dataframe[text_column_name].items():
            normalized = self._normalize_value(raw_value)
            if not normalized:
                skipped_count += 1
                continue

            if len(normalized) > self.max_document_chars:
                normalized = normalized[: self.max_document_chars].rstrip()
                truncated_count += 1

            row_number = self._resolve_row_number(row_index)
            documents.append(
                PreparedDocument(
                    row_number=row_number,
                    text=normalized,
                    source_text=normalized,
                    translated_to_english=False,
                    detected_language=None,
                )
            )

        if skipped_count:
            warnings.append(f"Skipped {skipped_count} empty or NaN row(s) before analysis.")
        if truncated_count:
            warnings.append(
                f"Trimmed {truncated_count} long response(s) to {self.max_document_chars} characters to keep the analysis stable."
            )

        return PreparedTextDataset(
            documents=documents,
            total_row_count=int(len(dataframe)),
            skipped_row_count=skipped_count,
            translated_document_count=0,
            warnings=warnings,
        )

    def _normalize_value(self, value: object) -> str:
        if pd.isna(value):
            return ""

        normalized = self.WHITESPACE_PATTERN.sub(" ", str(value)).strip()
        if not normalized:
            return ""
        if normalized.casefold() in self.PLACEHOLDER_VALUES:
            return ""
        return normalized

    @staticmethod
    def _resolve_row_number(row_index: object) -> int:
        if isinstance(row_index, int):
            return row_index + 1
        if isinstance(row_index, float) and row_index.is_integer():
            return int(row_index) + 1
        return 0


class TopicAnalysisKeywordService:
    STOPWORDS = frozenset(
        {
            "a",
            "about",
            "after",
            "again",
            "all",
            "also",
            "an",
            "and",
            "any",
            "are",
            "as",
            "at",
            "am",
            "be",
            "been",
            "being",
            "both",
            "but",
            "by",
            "can",
            "could",
            "do",
            "does",
            "each",
            "few",
            "for",
            "from",
            "had",
            "has",
            "have",
            "he",
            "her",
            "here",
            "hers",
            "herself",
            "him",
            "himself",
            "his",
            "how",
            "i",
            "if",
            "in",
            "into",
            "is",
            "it",
            "its",
            "me",
            "more",
            "most",
            "my",
            "need",
            "needs",
            "not",
            "of",
            "on",
            "only",
            "or",
            "other",
            "our",
            "ours",
            "ourselves",
            "out",
            "own",
            "please",
            "really",
            "same",
            "she",
            "should",
            "so",
            "that",
            "the",
            "their",
            "them",
            "then",
            "there",
            "these",
            "they",
            "this",
            "those",
            "to",
            "too",
            "us",
            "very",
            "was",
            "we",
            "were",
            "what",
            "when",
            "which",
            "who",
            "whom",
            "why",
            "will",
            "with",
            "would",
            "you",
            "your",
        }
    )
    TOKEN_PATTERN = re.compile(r"[^\W_][^\W_'\-]*", re.UNICODE)

    def top_terms(self, texts: list[str], *, top_n: int) -> list[str]:
        counts = Counter()
        for text in texts:
            counts.update(self._tokenize(text))
        return [term for term, count in counts.most_common() if count > 0][:top_n]

    def top_ngrams(self, texts: list[str], *, ngram_size: int, top_n: int) -> list[dict[str, int | str]]:
        counts = Counter()
        for text in texts:
            tokens = self._tokenize(text)
            if len(tokens) < ngram_size:
                continue
            counts.update(
                " ".join(tokens[index: index + ngram_size])
                for index in range(len(tokens) - ngram_size + 1)
            )

        return [
            {"term": term, "count": int(count)}
            for term, count in counts.most_common(top_n)
            if count > 0
        ]

    def top_ngrams_with_documents(
        self,
        documents: list[PreparedDocument],
        *,
        ngram_size: int,
        top_n: int,
    ) -> list[dict[str, object]]:
        counts = Counter()
        matched_documents: dict[str, list[dict[str, object]]] = defaultdict(list)
        for document in documents:
            tokens = self._tokenize(document.text)
            if len(tokens) < ngram_size:
                continue

            document_ngrams = [
                " ".join(tokens[index: index + ngram_size])
                for index in range(len(tokens) - ngram_size + 1)
            ]
            counts.update(document_ngrams)

            seen_terms: set[str] = set()
            for term in document_ngrams:
                if term in seen_terms or int(document.row_number) <= 0 or not document.text:
                    continue
                matched_documents[term].append(
                    {
                        "row_number": int(document.row_number),
                        "text": document.text,
                    }
                )
                seen_terms.add(term)

        return [
            {
                "term": term,
                "count": int(count),
                "document_count": len(matched_documents.get(term, [])),
                "_documents": matched_documents.get(term, []),
            }
            for term, count in counts.most_common(top_n)
            if count > 0
        ]

    def build_label(self, terms: list[str], *, fallback_prefix: str, fallback_id: str) -> str:
        if terms:
            return " / ".join(term.replace("_", " ") for term in terms[:3])
        return f"{fallback_prefix} {fallback_id}"

    def sanitize_terms(self, terms: Iterable[str], *, top_n: int | None = None) -> list[str]:
        cleaned_terms: list[str] = []
        seen_terms: set[str] = set()
        for term in terms:
            normalized = self._normalize_term(term)
            if not normalized:
                continue
            key = normalized.casefold()
            if key in seen_terms:
                continue
            seen_terms.add(key)
            cleaned_terms.append(normalized)
            if top_n is not None and len(cleaned_terms) >= top_n:
                break
        return cleaned_terms

    def top_phrase(self, texts: list[str]) -> str:
        trigrams = self.top_ngrams(texts, ngram_size=3, top_n=3)
        for item in trigrams:
            if int(item["count"]) >= 2:
                return str(item["term"])

        bigrams = self.top_ngrams(texts, ngram_size=2, top_n=3)
        for item in bigrams:
            if int(item["count"]) >= 2:
                return str(item["term"])

        terms = self.top_terms(texts, top_n=2)
        return " ".join(terms).strip()

    def _tokenize(self, text: str) -> list[str]:
        tokens: list[str] = []
        for token in self.TOKEN_PATTERN.findall(text.casefold()):
            normalized = token.strip("-'")
            if len(normalized) < 2:
                continue
            if normalized.isdigit():
                continue
            if normalized in self.STOPWORDS:
                continue
            tokens.append(normalized)
        return tokens

    def _normalize_term(self, term: object) -> str:
        ordered_tokens: list[str] = []
        seen_tokens: set[str] = set()
        for token in self._tokenize(str(term).replace("_", " ")):
            if token in seen_tokens:
                continue
            seen_tokens.add(token)
            ordered_tokens.append(token)
        return " ".join(ordered_tokens)


class TopicAnalysisNarrativeService:
    REQUEST_CUES = frozenset({"need", "needs", "more", "better", "clearer", "support", "help", "would", "could", "please", "want"})
    POSITIVE_CUES = frozenset({"love", "great", "helpful", "useful", "excellent", "amazing", "valuable", "enjoy", "good"})
    NEGATIVE_CUES = frozenset({"hard", "difficult", "issue", "problem", "frustrating", "missing", "lack", "limited", "confusing"})
    UNCERTAIN_CUES = frozenset({"unsure", "unclear", "unknown", "dont", "don't", "none", "nothing"})

    def __init__(self, keyword_service: TopicAnalysisKeywordService) -> None:
        self.keyword_service = keyword_service

    def build_label(
        self,
        *,
        texts: list[str],
        terms: list[str],
        is_noise: bool,
        fallback_prefix: str,
        fallback_id: str,
        prefer_terms: bool = False,
    ) -> str:
        if is_noise:
            return "Unassigned responses"

        phrase = self._build_phrase(texts=texts, terms=terms, prefer_terms=prefer_terms)
        if not phrase:
            return f"{fallback_prefix} {fallback_id}"

        intent = self._detect_intent(texts)
        if intent == "request":
            return f"Requests for {phrase}"
        if intent == "positive":
            return f"Positive feedback on {phrase}"
        if intent == "negative":
            return f"Challenges with {phrase}"
        if intent == "uncertain":
            return f"Unclear responses about {phrase}"
        return f"Responses about {phrase}"

    def build_comment(
        self,
        *,
        label: str,
        count: int,
        total_documents: int,
        examples: list[dict[str, object]],
    ) -> str:
        share = 0 if total_documents <= 0 else round((count / total_documents) * 100)
        row_numbers = [
            int(example["row_number"])
            for example in examples
            if isinstance(example, dict) and isinstance(example.get("row_number"), int)
        ]
        if not row_numbers:
            return f"{label} appears in {count} response(s), representing {share}% of the filtered sample."

        if len(row_numbers) == 1:
            reference_text = f"Representative document: row {row_numbers[0]}."
        else:
            joined = ", ".join(str(value) for value in row_numbers)
            reference_text = f"Representative documents: rows {joined}."

        return f"{label} appears in {count} response(s), representing {share}% of the filtered sample. {reference_text}"

    def _build_phrase(self, *, texts: list[str], terms: list[str], prefer_terms: bool = False) -> str:
        fallback_terms = [term.replace("_", " ").strip() for term in terms[:2] if term]
        if prefer_terms and fallback_terms:
            return self._normalize_phrase(" ".join(fallback_terms))

        phrase = self.keyword_service.top_phrase(texts).replace("_", " ").strip()
        if phrase:
            return self._normalize_phrase(phrase)

        return self._normalize_phrase(" ".join(fallback_terms))

    def _normalize_phrase(self, phrase: str) -> str:
        normalized = re.sub(r"\s+", " ", phrase).strip(" ,.-")
        return normalized.lower()

    def _detect_intent(self, texts: list[str]) -> str:
        scores = {"request": 0, "positive": 0, "negative": 0, "uncertain": 0}
        for text in texts:
            tokens = set()
            for token in self.keyword_service.TOKEN_PATTERN.findall(text.casefold()):
                normalized = token.strip("-'")
                if len(normalized) < 2:
                    continue
                if normalized.isdigit():
                    continue
                tokens.add(normalized)
            scores["request"] += sum(1 for token in tokens if token in self.REQUEST_CUES)
            scores["positive"] += sum(1 for token in tokens if token in self.POSITIVE_CUES)
            scores["negative"] += sum(1 for token in tokens if token in self.NEGATIVE_CUES)
            scores["uncertain"] += sum(1 for token in tokens if token in self.UNCERTAIN_CUES)

        best_intent = max(scores, key=scores.get)
        return best_intent if scores[best_intent] > 0 else "neutral"


class RepresentativeExampleSelectionService:
    def select(
        self,
        documents: list[PreparedDocument],
        *,
        terms: list[str],
        max_examples: int,
    ) -> list[dict[str, object]]:
        if not documents:
            return []

        lower_terms = [term.casefold() for term in terms if term]
        scored_documents: list[tuple[tuple[float, float, int], PreparedDocument]] = []
        for document in documents:
            lowered = document.text.casefold()
            term_hits = sum(1 for term in lower_terms if term in lowered)
            length_target = abs(len(document.text) - 220)
            score = (float(term_hits), -float(length_target), -document.row_number)
            scored_documents.append((score, document))

        scored_documents.sort(key=lambda item: item[0], reverse=True)
        examples: list[dict[str, object]] = []
        seen_texts: set[str] = set()
        for _, document in scored_documents:
            dedupe_key = document.text.casefold()
            if dedupe_key in seen_texts:
                continue
            seen_texts.add(dedupe_key)
            examples.append(
                {
                    "row_number": int(document.row_number),
                    "text": document.text,
                    "source_text": None,
                    "translated": False,
                }
            )
            if len(examples) >= max_examples:
                break
        return examples


class SentenceEmbeddingService:
    def __init__(self) -> None:
        self._models: dict[str, object] = {}
        self._lock = Lock()

    def _get_model(self, model_name: str):
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as exc:  # pragma: no cover - dependency error path
            raise TopicAnalysisDependencyError(
                "sentence-transformers is required for embedding-based analysis."
            ) from exc

        with self._lock:
            model = self._models.get(model_name)
            if model is None:
                model = SentenceTransformer(model_name)
                self._models[model_name] = model
        return model

    def warm_up(self, *, model_name: str) -> None:
        if not model_name:
            return
        self._get_model(model_name)

    def encode(self, texts: list[str], *, model_name: str):
        if not texts:
            return []

        try:
            import numpy as np
        except Exception as exc:  # pragma: no cover - dependency error path
            raise TopicAnalysisDependencyError(
                "numpy is required for embedding-based analysis."
            ) from exc

        model = self._get_model(model_name)

        embeddings = model.encode(
            texts,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return np.array(embeddings)


class NgramAnalysisService:
    def __init__(self, keyword_service: TopicAnalysisKeywordService) -> None:
        self.keyword_service = keyword_service

    def run(self, documents: list[PreparedDocument], *, top_n: int) -> list[dict[str, object]]:
        return [
            {
                "label": "Single Words",
                "ngram_size": 1,
                "items": self.keyword_service.top_ngrams_with_documents(documents, ngram_size=1, top_n=top_n),
            },
            {
                "label": "Two-Word Phrases",
                "ngram_size": 2,
                "items": self.keyword_service.top_ngrams_with_documents(documents, ngram_size=2, top_n=top_n),
            },
            {
                "label": "Three-Word Phrases",
                "ngram_size": 3,
                "items": self.keyword_service.top_ngrams_with_documents(documents, ngram_size=3, top_n=top_n),
            },
        ]


class KMeansAnalysisService:
    def run(self, embeddings, *, requested_clusters: int, random_state: int) -> dict[str, object]:
        try:
            import numpy as np
            from sklearn.cluster import KMeans, MiniBatchKMeans
        except Exception as exc:  # pragma: no cover - dependency error path
            raise TopicAnalysisDependencyError(
                "scikit-learn and numpy are required for KMeans analysis."
            ) from exc

        if getattr(embeddings, "shape", (0,))[0] == 0:
            return {"assignments": [], "warnings": []}

        n_samples = int(embeddings.shape[0])
        if n_samples == 1:
            return {
                "assignments": [0] * n_samples,
                "warnings": ["All usable responses collapsed into a single group."],
            }

        n_clusters = max(2, min(requested_clusters, n_samples))
        warnings: list[str] = []

        # MiniBatchKMeans is 3–5× faster for large datasets with negligible quality loss.
        # For small datasets, standard KMeans with elkan algorithm converges faster on
        # dense normalized vectors than the default lloyd implementation.
        if n_samples >= 1000:
            model = MiniBatchKMeans(
                n_clusters=n_clusters,
                random_state=random_state,
                n_init=3,
                batch_size=min(1024, n_samples),
            )
        else:
            model = KMeans(
                n_clusters=n_clusters,
                random_state=random_state,
                n_init=3,
                algorithm="elkan",
            )

        labels = model.fit_predict(embeddings)
        if n_clusters < requested_clusters:
            warnings.append(
                f"Response Groups reduced the number of groups to {n_clusters} because the filtered sample was smaller than the configured target."
            )

        return {
            "assignments": [int(value) for value in labels.tolist()],
            "warnings": warnings,
        }


class HdbscanAnalysisService:
    def run(
        self,
        embeddings,
        *,
        min_cluster_size: int,
        min_samples: int,
        metric: str,
    ) -> dict[str, object]:
        try:
            import hdbscan
        except Exception as exc:  # pragma: no cover - dependency error path
            raise TopicAnalysisDependencyError(
                "hdbscan is required for density-based analysis."
            ) from exc

        if getattr(embeddings, "shape", (0,))[0] == 0:
            return {"assignments": [], "warnings": []}

        n_samples = int(embeddings.shape[0])
        cluster_size = max(2, min(min_cluster_size, n_samples))
        sample_floor = max(1, min(min_samples, cluster_size))
        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=cluster_size,
            min_samples=sample_floor,
            metric=metric,
        )
        labels = clusterer.fit_predict(embeddings)

        warnings: list[str] = []
        if all(int(label) == -1 for label in labels.tolist()):
            warnings.append(
                "Natural Groups could not find clear groups in the current filtered sample."
            )

        return {
            "assignments": [int(value) for value in labels.tolist()],
            "warnings": warnings,
        }


class BertopicAnalysisService:
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
        try:
            import numpy as np
            import umap
            from bertopic import BERTopic
            from bertopic.vectorizers import ClassTfidfTransformer
            from sklearn.decomposition import PCA
            from sklearn.feature_extraction.text import CountVectorizer
        except Exception as exc:  # pragma: no cover - dependency error path
            raise TopicAnalysisDependencyError(
                "BERTopic, umap-learn, and scikit-learn are required for BERTopic analysis."
            ) from exc

        # PCA pre-reduction: bring embeddings from ~384 dims down to 50 before UMAP.
        # UMAP computation scales with input dimensionality; this alone cuts UMAP time by ~60%
        # while preserving neighbourhood structure (PCA is a linear projection that keeps the
        # most informative variance). Only applied when the dataset is large enough for PCA to
        # be meaningful.
        embedding_array = np.asarray(embeddings)
        reduced_embeddings = embedding_array
        if (
            embedding_array.ndim == 2
            and embedding_array.shape[0] >= 10
            and embedding_array.shape[1] > 50
        ):
            n_pca = min(50, embedding_array.shape[1], embedding_array.shape[0] - 1)
            if n_pca >= 2:
                reduced_embeddings = PCA(n_components=n_pca, random_state=42).fit_transform(embedding_array)

        vectorizer = CountVectorizer(
            stop_words=sorted(TopicAnalysisKeywordService.STOPWORDS),
            min_df=1,
            max_df=0.95,
            ngram_range=(1, 2),
            lowercase=True,
        )
        ctfidf = ClassTfidfTransformer(reduce_frequent_words=True)
        umap_model = umap.UMAP(
            # n_neighbors=10 is faster than 15 with minimal quality loss for BERTopic clustering.
            n_neighbors=min(10, max(2, len(texts) - 1)),
            n_components=min(5, max(2, len(texts) - 1)),
            min_dist=0.0,
            # "euclidean" is mathematically equivalent to "cosine" for L2-normalised embeddings
            # (produced by SentenceEmbeddingService) and is significantly faster in UMAP's
            # internal approximate nearest-neighbour search.
            metric="euclidean",
            random_state=42,
        )
        topic_model = BERTopic(
            vectorizer_model=vectorizer,
            ctfidf_model=ctfidf,
            umap_model=umap_model,
            language=language,
            # False is the BERTopic default and skips the expensive secondary UMAP pass that
            # computes per-document topic probability distributions. The probability array
            # is already discarded (topics, _ = ...) so setting True was pure overhead.
            calculate_probabilities=False,
            verbose=False,
            nr_topics="auto",
        )

        topics, _ = topic_model.fit_transform(texts, reduced_embeddings)
        warnings: list[str] = []
        topics = [int(value) for value in topics]
        topics, reduction_warnings = self._reduce_topic_outliers(
            topic_model,
            texts=texts,
            topics=topics,
            embeddings=reduced_embeddings,
            enabled=reduce_outliers,
            threshold=outlier_threshold,
        )
        warnings.extend(reduction_warnings)
        info = topic_model.get_topic_info().copy()

        groups: dict[str, dict[str, object]] = {}
        for _, row in info.iterrows():
            topic_id = int(row["Topic"])
            words = topic_model.get_topic(topic_id) or []
            terms = [word for word, _score in words[:top_terms] if word]
            groups[str(topic_id)] = {
                "label": self._format_label(topic_id=topic_id, terms=terms),
                "terms": terms,
                "is_noise": topic_id == -1,
            }

        return {
            "assignments": [int(value) for value in topics],
            "groups": groups,
            "warnings": warnings,
        }

    @staticmethod
    def _reduce_topic_outliers(
        topic_model,
        *,
        texts: list[str],
        topics: list[int],
        embeddings,
        enabled: bool,
        threshold: float,
    ) -> tuple[list[int], list[str]]:
        if not enabled or not topics or not any(topic == -1 for topic in topics):
            return topics, []

        try:
            new_topics = topic_model.reduce_outliers(
                texts,
                topics,
                strategy="embeddings",
                embeddings=embeddings,
                threshold=max(0.0, float(threshold)),
            )
        except Exception:
            return topics, ["BERTopic kept some responses unassigned because outlier reassignment was unavailable."]

        normalized_topics = [int(value) for value in new_topics]
        reassigned_count = sum(1 for original, updated in zip(topics, normalized_topics) if original == -1 and updated != -1)
        if reassigned_count <= 0:
            return normalized_topics, []

        try:
            topic_model.update_topics(texts, topics=normalized_topics)
        except Exception:
            return topics, ["BERTopic kept some responses unassigned because outlier reassignment was unavailable."]
        warnings = [
            f"BERTopic reassigned {reassigned_count} response(s) from the outlier bucket to the nearest existing theme."
        ]
        remaining_outliers = sum(1 for topic in normalized_topics if topic == -1)
        if remaining_outliers:
            warnings.append(f"{remaining_outliers} response(s) remained unassigned after BERTopic outlier reassignment.")
        return normalized_topics, warnings

    @staticmethod
    def _format_label(*, topic_id: int, terms: list[str]) -> str:
        if topic_id == -1:
            return "Unassigned responses"
        if terms:
            return " / ".join(term.replace("_", " ") for term in terms[:3])
        return f"Theme {topic_id}"


class TopicAnalysisService:
    def __init__(
        self,
        *,
        config: TopicAnalysisConfig,
        input_validation_service: TopicAnalysisInputValidationService,
        text_preparation_service: TopicAnalysisTextPreparationService,
        keyword_service: TopicAnalysisKeywordService,
        narrative_service: TopicAnalysisNarrativeService,
        representative_example_service: RepresentativeExampleSelectionService,
        embedding_service: SentenceEmbeddingService,
        ngram_service: NgramAnalysisService,
        kmeans_service: KMeansAnalysisService,
        hdbscan_service: HdbscanAnalysisService,
        bertopic_service: BertopicAnalysisService,
        ai_label_service: TopicAiLabelService | None = None,
    ) -> None:
        self.config = config
        self.input_validation_service = input_validation_service
        self.text_preparation_service = text_preparation_service
        self.keyword_service = keyword_service
        self.narrative_service = narrative_service
        self.representative_example_service = representative_example_service
        self.embedding_service = embedding_service
        self.ngram_service = ngram_service
        self.kmeans_service = kmeans_service
        self.hdbscan_service = hdbscan_service
        self.bertopic_service = bertopic_service
        self.ai_label_service = ai_label_service

    def warm_up(self) -> None:
        self.text_preparation_service.warm_up()
        self.embedding_service.warm_up(model_name=self.config.embedding_model)

    def run(
        self,
        *,
        result_id: str,
        dataframe: pd.DataFrame,
        model_key: str,
        text_column_name: str,
        available_verbatim_columns: Iterable[str],
    ) -> dict[str, object]:
        model_label = self.input_validation_service.get_model_label(model_key)
        base_response: dict[str, object] = {
            "ok": False,
            "result_id": result_id,
            "model_key": model_key,
            "model_label": model_label,
            "text_column_name": text_column_name,
            "filtered_row_count": int(len(dataframe)),
            "valid_document_count": 0,
            "skipped_document_count": 0,
            "translated_document_count": 0,
            "warnings": [],
            "error": None,
            "groups": [],
            "ngram_buckets": [],
            "scatter_points": [],
        }

        try:
            self.input_validation_service.validate_request(
                model_key=model_key,
                text_column_name=text_column_name,
                available_verbatim_columns=available_verbatim_columns,
            )
            prepared = self.text_preparation_service.prepare(
                dataframe,
                text_column_name=text_column_name,
            )
            warnings = self.input_validation_service.validate_dataset(
                prepared,
                model_key=model_key,
            )
            base_response["valid_document_count"] = int(len(prepared.documents))
            base_response["skipped_document_count"] = int(prepared.skipped_row_count)
            base_response["warnings"] = warnings

            embeddings = None
            if model_key == "ngrams":
                ngram_buckets = self.ngram_service.run(
                    prepared.documents,
                    top_n=self.config.top_ngrams_per_bucket,
                )
                translated_bucket_count, translation_warnings = self._translate_ngram_buckets(ngram_buckets)
                warnings.extend(translation_warnings)
                base_response["warnings"] = warnings
                base_response["ok"] = True
                base_response["translated_document_count"] = translated_bucket_count
                base_response["ngram_buckets"] = ngram_buckets
                return base_response

            if model_key == "bertopic":
                embeddings = self.embedding_service.encode(
                    prepared.texts,
                    model_name=self.config.embedding_model,
                )
                model_result = self.bertopic_service.run(
                    prepared.texts,
                    embeddings,
                    top_terms=self.config.top_terms_per_group,
                    language=self.config.bertopic_language,
                    reduce_outliers=self.config.bertopic_reduce_outliers,
                    outlier_threshold=self.config.bertopic_outlier_threshold,
                )
            else:
                embeddings = self.embedding_service.encode(
                    prepared.texts,
                    model_name=self.config.embedding_model,
                )
                # PCA pre-reduction for K-means: 384 → 50 dims.
                # Improves cluster quality (fewer dimensions → less curse of dimensionality)
                # and speeds up clustering. The reduced embeddings are reused for scatter
                # projection so PCA runs only once per analysis.
                kmeans_embeddings = embeddings
                if model_key == "kmeans":
                    try:
                        import numpy as np
                        from sklearn.decomposition import PCA as _PCA
                        _arr = np.asarray(embeddings)
                        if (
                            _arr.ndim == 2
                            and _arr.shape[0] >= 10
                            and _arr.shape[1] > 50
                        ):
                            _n_pca = min(50, _arr.shape[1], _arr.shape[0] - 1)
                            if _n_pca >= 2:
                                kmeans_embeddings = _PCA(
                                    n_components=_n_pca, random_state=42
                                ).fit_transform(_arr)
                    except Exception:  # pragma: no cover - sklearn always present
                        pass
                    model_result = self.kmeans_service.run(
                        kmeans_embeddings,
                        requested_clusters=self.config.kmeans_clusters,
                        random_state=self.config.kmeans_random_state,
                    )
                elif model_key == "hdbscan":
                    model_result = self.hdbscan_service.run(
                        embeddings,
                        min_cluster_size=self.config.hdbscan_min_cluster_size,
                        min_samples=self.config.hdbscan_min_samples,
                        metric=self.config.hdbscan_metric,
                    )
                else:  # pragma: no cover - guarded by request validation
                    raise TopicAnalysisInputError(f"Unsupported analysis mode '{model_key}'.")

            warnings.extend(model_result.get("warnings", []))
            groups = self._build_groups(
                documents=prepared.documents,
                assignments=[int(value) for value in model_result.get("assignments", [])],
                explicit_groups=model_result.get("groups", {}),
                model_key=model_key,
            )
            _, ai_warnings = self._apply_ai_labels(
                groups,
                model_key=model_key,
                text_column_name=text_column_name,
            )
            warnings.extend(ai_warnings)
            translated_group_count, translation_warnings = self._translate_group_outputs(groups)
            warnings.extend(translation_warnings)
            base_response["warnings"] = warnings
            base_response["translated_document_count"] = translated_group_count
            base_response["groups"] = groups
            if model_key == "kmeans" and embeddings is not None:
                base_response["scatter_points"] = self._build_scatter_points(
                    documents=prepared.documents,
                    assignments=[int(value) for value in model_result.get("assignments", [])],
                    embeddings=kmeans_embeddings,
                    groups=groups,
                )
            base_response["ok"] = True
            return base_response
        except (TopicAnalysisInputError, TopicAnalysisDependencyError) as exc:
            base_response["error"] = str(exc)
            return base_response
        except Exception as exc:  # pragma: no cover - defensive guard
            base_response["error"] = f"Analysis failed unexpectedly: {exc}"
            return base_response

    def _pretranslate_bertopic_groups(
        self,
        grouped_documents: dict[int, list[PreparedDocument]],
        ordered_group_ids: list[int],
        explicit_groups: dict[str, dict[str, object]],
    ) -> None:
        """Warm the translation cache for all BERTopic group samples and terms in one batch.

        Without this, _build_bertopic_display_context is called once per group, each time
        making a separate Google Translate API request (2 × N_groups serial calls). By
        collecting every text and term up-front and passing them through the translation
        service in a single call, subsequent per-group calls become instant cache hits.
        """
        translation_service = self.text_preparation_service.translation_service
        if translation_service is None:
            return

        all_texts: list[str] = []
        for group_id in ordered_group_ids:
            grouped_rows = grouped_documents[group_id]
            grouped_texts = [doc.text for doc in grouped_rows]

            sample_size = max(2, min(len(grouped_texts), self.config.representative_examples_per_group + 1))
            all_texts.extend(self._sample_group_texts(grouped_texts, limit=sample_size))

            explicit_group = explicit_groups.get(str(group_id), {})
            terms = [
                str(t)
                for t in explicit_group.get("terms", [])
                if isinstance(t, str) and str(t).strip()
            ]
            terms = self.keyword_service.sanitize_terms(terms, top_n=self.config.top_terms_per_group)
            if not terms:
                terms = self.keyword_service.top_terms(grouped_texts, top_n=self.config.top_terms_per_group)
            all_texts.extend(terms)

        if all_texts:
            translation_service.translate(all_texts)

    def _build_groups(
        self,
        *,
        documents: list[PreparedDocument],
        assignments: list[int],
        explicit_groups: dict[str, dict[str, object]],
        model_key: str,
    ) -> list[dict[str, object]]:
        grouped_documents: dict[int, list[PreparedDocument]] = defaultdict(list)
        for assignment, document in zip(assignments, documents):
            grouped_documents[int(assignment)].append(document)

        total_documents = max(1, len(documents))
        groups: list[dict[str, object]] = []
        ordered_group_ids = sorted(
            grouped_documents.keys(),
            key=lambda group_id: (-len(grouped_documents[group_id]), group_id),
        )

        # For BERTopic, pre-warm the translation cache with one batched API call covering
        # all groups, so the per-group calls in _build_bertopic_display_context are cache hits.
        if model_key == "bertopic":
            self._pretranslate_bertopic_groups(grouped_documents, ordered_group_ids, explicit_groups)

        for group_id in ordered_group_ids:
            group_key = str(group_id)
            grouped_rows = grouped_documents[group_id]
            grouped_texts = [document.text for document in grouped_rows]
            explicit_group = explicit_groups.get(group_key, {})
            terms = [
                str(term)
                for term in explicit_group.get("terms", [])
                if isinstance(term, str) and term.strip()
            ]
            terms = self.keyword_service.sanitize_terms(
                terms,
                top_n=self.config.top_terms_per_group,
            )
            if not terms:
                terms = self.keyword_service.top_terms(
                    grouped_texts,
                    top_n=self.config.top_terms_per_group,
                )

            is_noise = bool(explicit_group.get("is_noise", group_id == -1))
            fallback_prefix = "Theme" if model_key == "bertopic" else "Group"
            display_texts = grouped_texts
            display_terms = list(terms)
            label_translation_warnings: list[str] = []

            if model_key == "bertopic":
                display_texts, display_terms, label_translation_warnings = self._build_bertopic_display_context(
                    grouped_texts=grouped_texts,
                    terms=terms,
                )

            raw_label = self.narrative_service.build_label(
                texts=grouped_texts,
                terms=terms,
                is_noise=is_noise,
                fallback_prefix=fallback_prefix,
                fallback_id=group_key,
                prefer_terms=model_key == "bertopic",
            )
            label = self.narrative_service.build_label(
                texts=display_texts,
                terms=display_terms,
                is_noise=is_noise,
                fallback_prefix=fallback_prefix,
                fallback_id=group_key,
                prefer_terms=model_key == "bertopic",
            )
            examples = self.representative_example_service.select(
                grouped_rows,
                terms=terms,
                max_examples=self.config.representative_examples_per_group,
            )
            comment = self.narrative_service.build_comment(
                label=label,
                count=int(len(grouped_rows)),
                total_documents=total_documents,
                examples=examples,
            )
            groups.append(
                {
                    "group_id": group_key,
                    "label": label,
                    "source_label": raw_label if label != raw_label else None,
                    "translated": label != raw_label,
                    "ai_generated": False,
                    "comment": comment,
                    "count": int(len(grouped_rows)),
                    "share": round(len(grouped_rows) / total_documents, 4),
                    "total_documents": total_documents,
                    "terms": display_terms,
                    "examples": examples,
                    "is_noise": is_noise,
                    "_documents": [
                        {
                            "row_number": int(document.row_number),
                            "text": document.text,
                        }
                        for document in grouped_rows
                        if int(document.row_number) > 0 and document.text
                    ],
                    "_label_translation_warnings": label_translation_warnings,
                }
            )

        return groups

    def _build_bertopic_display_context(
        self,
        *,
        grouped_texts: list[str],
        terms: list[str],
    ) -> tuple[list[str], list[str], list[str]]:
        translation_service = self.text_preparation_service.translation_service
        if translation_service is None:
            return grouped_texts, list(terms), []

        warnings: list[str] = []
        sample_size = max(2, min(len(grouped_texts), self.config.representative_examples_per_group + 1))
        sampled_texts = self._sample_group_texts(grouped_texts, limit=sample_size)
        display_texts = list(grouped_texts)
        if sampled_texts:
            sample_result = translation_service.translate(sampled_texts)
            warnings.extend(sample_result.warnings)
            if sample_result.translated_count:
                display_texts = sample_result.texts

        display_terms = self.keyword_service.sanitize_terms(
            terms,
            top_n=self.config.top_terms_per_group,
        )
        if terms:
            term_result = translation_service.translate(terms)
            warnings.extend(term_result.warnings)
            if term_result.translated_count:
                translated_terms = [
                    translated.strip() if translated_flag and translated.strip() else source
                    for source, translated, translated_flag in zip(
                        terms,
                        term_result.texts,
                        term_result.translated_flags,
                    )
                ]
                display_terms = self.keyword_service.sanitize_terms(
                    translated_terms,
                    top_n=self.config.top_terms_per_group,
                )

        return display_texts, display_terms, warnings

    @staticmethod
    def _sample_group_texts(grouped_texts: list[str], *, limit: int) -> list[str]:
        unique_texts: list[str] = []
        seen: set[str] = set()
        for text in grouped_texts:
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            unique_texts.append(text)
            if len(unique_texts) >= limit:
                break
        return unique_texts

    def _apply_ai_labels(
        self,
        groups: list[dict[str, object]],
        *,
        model_key: str,
        text_column_name: str,
    ) -> tuple[int, list[str]]:
        if self.ai_label_service is None or not groups:
            return 0, []

        try:
            result = self.ai_label_service.label_groups(
                groups,
                model_key=model_key,
                text_column_name=text_column_name,
            )
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.info("AI topic labeling failed unexpectedly: %s", exc)
            return 0, ["AI topic labeling was skipped and heuristic labels were kept."]

        relabeled_count = 0
        for group in groups:
            group_id = str(group.get("group_id", "")).strip()
            new_label = result.labels_by_group_id.get(group_id, "").strip()
            current_label = str(group.get("label", "")).strip()
            if not new_label or not current_label or new_label == current_label:
                continue

            group["source_label"] = current_label
            group["label"] = new_label
            group["translated"] = False
            group["ai_generated"] = True
            relabeled_count += 1

        for group in groups:
            count = int(group.get("count", 0))
            total_documents = max(1, int(group.get("total_documents", count)))
            group["comment"] = self.narrative_service.build_comment(
                label=str(group.get("label", "Group")),
                count=count,
                total_documents=total_documents,
                examples=[
                    example
                    for example in group.get("examples", [])
                    if isinstance(example, dict)
                ],
            )

        warnings = list(result.warnings)
        if relabeled_count:
            warnings.append(f"AI generated clearer labels for {relabeled_count} group(s).")
        return relabeled_count, warnings

    def _translate_group_outputs(self, groups: list[dict[str, object]]) -> tuple[int, list[str]]:
        translation_service = self.text_preparation_service.translation_service
        if translation_service is None or not groups:
            return 0, []

        warnings: list[str] = []
        translated_label_count = sum(1 for group in groups if bool(group.get("translated")))
        translated_example_count = 0
        for group in groups:
            warnings.extend(
                str(message)
                for message in group.pop("_label_translation_warnings", [])
                if isinstance(message, str) and message.strip()
            )

        untranslated_groups = [
            group
            for group in groups
            if not bool(group.get("translated")) and not bool(group.get("ai_generated"))
        ]
        if untranslated_groups:
            label_texts = [str(group.get("label", "")).strip() for group in untranslated_groups]
            label_result = translation_service.translate(label_texts)
            warnings.extend(label_result.warnings)
            for group, source_label, translated_label, translated_flag in zip(
                untranslated_groups,
                label_texts,
                label_result.texts,
                label_result.translated_flags,
            ):
                if translated_flag and translated_label.strip():
                    group["source_label"] = source_label
                    group["label"] = translated_label.strip()
                    group["translated"] = True
                    translated_label_count += 1
                else:
                    group["source_label"] = None
                    group["translated"] = False

        example_records: list[dict[str, object]] = []
        example_texts: list[str] = []
        for group in groups:
            for example in group.get("examples", []):
                if not isinstance(example, dict):
                    continue
                example_text = str(example.get("text", "")).strip()
                if not example_text:
                    continue
                example_records.append(example)
                example_texts.append(example_text)

        if example_texts:
            example_result = translation_service.translate(example_texts)
            warnings.extend(example_result.warnings)
            for example, source_text, translated_text, translated_flag in zip(
                example_records,
                example_texts,
                example_result.texts,
                example_result.translated_flags,
            ):
                if translated_flag and translated_text.strip():
                    example["source_text"] = source_text
                    example["text"] = translated_text.strip()
                    example["translated"] = True
                    translated_example_count += 1
                else:
                    example["source_text"] = None
                    example["translated"] = False

        for group in groups:
            count = int(group.get("count", 0))
            total_documents = max(1, int(group.get("total_documents", count)))
            group["comment"] = self.narrative_service.build_comment(
                label=str(group.get("label", "Group")),
                count=count,
                total_documents=total_documents,
                examples=[
                    example
                    for example in group.get("examples", [])
                    if isinstance(example, dict)
                ],
            )

        translated_count = translated_label_count + translated_example_count
        if translated_count:
            warnings.append(
                f"Translated {translated_label_count} group label(s) and {translated_example_count} representative response(s) to English for display after grouping."
            )
        return translated_count, warnings

    def _translate_ngram_buckets(self, buckets: list[dict[str, object]]) -> tuple[int, list[str]]:
        translation_service = self.text_preparation_service.translation_service
        if translation_service is None or not buckets:
            return 0, []

        warnings: list[str] = []
        items: list[dict[str, object]] = []
        texts: list[str] = []
        for bucket in buckets:
            for item in bucket.get("items", []):
                if not isinstance(item, dict):
                    continue
                term = str(item.get("term", "")).strip()
                if not term:
                    continue
                items.append(item)
                texts.append(term)

        if not texts:
            return 0, []

        translation_result = translation_service.translate(texts)
        warnings.extend(translation_result.warnings)

        translated_count = 0
        for item, source_term, translated_term, translated_flag in zip(
            items,
            texts,
            translation_result.texts,
            translation_result.translated_flags,
        ):
            cleaned_translation = self.keyword_service.sanitize_terms(
                [translated_term],
                top_n=1,
            )
            display_term = cleaned_translation[0] if cleaned_translation else translated_term.strip()
            if translated_flag and display_term:
                item["source_term"] = source_term
                item["term"] = display_term
                item["translated"] = True
                translated_count += 1
            else:
                item["source_term"] = None
                item["translated"] = False

        if translated_count:
            warnings.append(
                f"Translated {translated_count} common phrase(s) to English for display after analysis."
            )
        return translated_count, warnings

    def _build_scatter_points(
        self,
        *,
        documents: list[PreparedDocument],
        assignments: list[int],
        embeddings,
        groups: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        if not documents or not assignments:
            return []

        try:
            import numpy as np
            from sklearn.decomposition import PCA
        except Exception as exc:  # pragma: no cover - dependency error path
            raise TopicAnalysisDependencyError(
                "scikit-learn and numpy are required for K-means scatter plots."
            ) from exc

        embedding_array = np.asarray(embeddings)
        if embedding_array.ndim != 2 or embedding_array.shape[0] == 0:
            return []

        if embedding_array.shape[1] > 2 and embedding_array.shape[0] >= 2:
            # Input may already be PCA-reduced to ~50 dims; PCA from 50→2 is ~7× faster
            # than from 384→2 because SVD cost scales with d².
            projected = PCA(n_components=2, random_state=self.config.kmeans_random_state).fit_transform(embedding_array)
        elif embedding_array.shape[1] == 2:
            projected = embedding_array
        elif embedding_array.shape[1] == 1:
            x_axis = embedding_array[:, 0]
            y_axis = np.zeros_like(x_axis)
            projected = np.column_stack((x_axis, y_axis))
        else:
            projected = np.zeros((embedding_array.shape[0], 2))

        group_labels = {
            str(group.get("group_id", "")): str(group.get("label", "Unlabelled group"))
            for group in groups
        }

        scatter_points: list[dict[str, object]] = []
        for index, (document, assignment) in enumerate(zip(documents, assignments)):
            group_key = str(int(assignment))
            scatter_points.append(
                {
                    "row_number": int(document.row_number),
                    "text": document.text,
                    "group_id": group_key,
                    "group_label": group_labels.get(group_key, "Unlabelled group"),
                    "x": float(projected[index][0]),
                    "y": float(projected[index][1]),
                }
            )

        return scatter_points
