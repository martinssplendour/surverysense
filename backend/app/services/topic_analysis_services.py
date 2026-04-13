from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import math
import re
from threading import Lock
from typing import Any, Iterable

import pandas as pd

from app.core.exceptions import (
    TopicAnalysisDependencyError,
    TopicAnalysisInputError,
)


MODEL_LABELS = {
    "bertopic": "AI Themes",
    "kmeans": "Response Groups",
    "hdbscan": "Natural Groups",
    "ngrams": "Common Phrases",
}


@dataclass(slots=True)
class TopicAnalysisConfig:
    embedding_model: str
    kmeans_clusters: int
    kmeans_random_state: int
    hdbscan_min_cluster_size: int
    hdbscan_min_samples: int
    hdbscan_metric: str
    bertopic_language: str
    top_terms_per_group: int
    top_ngrams_per_bucket: int
    representative_examples_per_group: int
    max_document_chars: int


@dataclass(slots=True)
class PreparedDocument:
    row_number: int
    text: str


@dataclass(slots=True)
class PreparedTextDataset:
    documents: list[PreparedDocument]
    total_row_count: int
    skipped_row_count: int
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

    def __init__(self, *, max_document_chars: int) -> None:
        self.max_document_chars = max(200, max_document_chars)

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
            documents.append(PreparedDocument(row_number=row_number, text=normalized))

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
    TOKEN_PATTERN = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9][A-Za-zÀ-ÖØ-öø-ÿ0-9'\-]*")
    STOPWORDS = frozenset(
        {
            "a",
            "an",
            "and",
            "are",
            "as",
            "at",
            "be",
            "been",
            "being",
            "but",
            "by",
            "can",
            "could",
            "do",
            "does",
            "for",
            "from",
            "had",
            "has",
            "have",
            "i",
            "if",
            "in",
            "into",
            "is",
            "it",
            "its",
            "me",
            "more",
            "my",
            "need",
            "needs",
            "not",
            "of",
            "on",
            "or",
            "our",
            "please",
            "really",
            "so",
            "that",
            "the",
            "their",
            "them",
            "there",
            "these",
            "they",
            "this",
            "to",
            "us",
            "was",
            "we",
            "were",
            "what",
            "when",
            "which",
            "with",
            "would",
            "you",
            "your",
        }
    )

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

    def build_label(self, terms: list[str], *, fallback_prefix: str, fallback_id: str) -> str:
        if terms:
            return " / ".join(term.replace("_", " ") for term in terms[:3])
        return f"{fallback_prefix} {fallback_id}"

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
    ) -> str:
        if is_noise:
            return "Mixed or unclear responses"

        phrase = self._build_phrase(texts=texts, terms=terms)
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

    def _build_phrase(self, *, texts: list[str], terms: list[str]) -> str:
        phrase = self.keyword_service.top_phrase(texts).replace("_", " ").strip()
        if phrase:
            return self._normalize_phrase(phrase)

        fallback_terms = [term.replace("_", " ").strip() for term in terms[:2] if term]
        return self._normalize_phrase(" ".join(fallback_terms))

    def _normalize_phrase(self, phrase: str) -> str:
        normalized = re.sub(r"\s+", " ", phrase).strip(" ,.-")
        return normalized.lower()

    def _detect_intent(self, texts: list[str]) -> str:
        scores = {"request": 0, "positive": 0, "negative": 0, "uncertain": 0}
        for text in texts:
            tokens = set(self.keyword_service._tokenize(text))
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

    def run(self, texts: list[str], *, top_n: int) -> list[dict[str, object]]:
        return [
            {
                "label": "Single Words",
                "ngram_size": 1,
                "items": self.keyword_service.top_ngrams(texts, ngram_size=1, top_n=top_n),
            },
            {
                "label": "Two-Word Phrases",
                "ngram_size": 2,
                "items": self.keyword_service.top_ngrams(texts, ngram_size=2, top_n=top_n),
            },
            {
                "label": "Three-Word Phrases",
                "ngram_size": 3,
                "items": self.keyword_service.top_ngrams(texts, ngram_size=3, top_n=top_n),
            },
        ]


class KMeansAnalysisService:
    def run(self, embeddings, *, requested_clusters: int, random_state: int) -> dict[str, object]:
        try:
            import numpy as np
            from sklearn.cluster import KMeans
        except Exception as exc:  # pragma: no cover - dependency error path
            raise TopicAnalysisDependencyError(
                "scikit-learn and numpy are required for KMeans analysis."
            ) from exc

        if getattr(embeddings, "shape", (0,))[0] == 0:
            return {"assignments": [], "warnings": []}

        n_samples = int(embeddings.shape[0])
        unique_rows = np.unique(embeddings, axis=0)
        if n_samples == 1 or unique_rows.shape[0] == 1:
            return {
                "assignments": [0] * n_samples,
                "warnings": ["All usable responses collapsed into a single group."],
            }

        n_clusters = max(2, min(requested_clusters, n_samples, unique_rows.shape[0]))
        model = KMeans(n_clusters=n_clusters, random_state=random_state, n_init="auto")
        labels = model.fit_predict(embeddings)
        warnings: list[str] = []
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
        *,
        top_terms: int,
        language: str,
    ) -> dict[str, object]:
        try:
            import umap
            from bertopic import BERTopic
            from bertopic.vectorizers import ClassTfidfTransformer
            from sklearn.feature_extraction.text import CountVectorizer
        except Exception as exc:  # pragma: no cover - dependency error path
            raise TopicAnalysisDependencyError(
                "BERTopic, umap-learn, and scikit-learn are required for BERTopic analysis."
            ) from exc

        vectorizer = CountVectorizer(
            stop_words="english",
            min_df=1,
            max_df=0.95,
            ngram_range=(1, 2),
            lowercase=True,
        )
        ctfidf = ClassTfidfTransformer(reduce_frequent_words=True)
        umap_model = umap.UMAP(
            n_neighbors=min(15, max(2, len(texts) - 1)),
            n_components=min(5, max(2, len(texts) - 1)),
            min_dist=0.0,
            metric="cosine",
            random_state=42,
        )
        topic_model = BERTopic(
            vectorizer_model=vectorizer,
            ctfidf_model=ctfidf,
            umap_model=umap_model,
            language=language,
            calculate_probabilities=True,
            verbose=False,
            nr_topics="auto",
        )

        topics, _ = topic_model.fit_transform(texts)
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
            "warnings": [],
        }

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

    def warm_up(self) -> None:
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

            if model_key == "ngrams":
                base_response["ok"] = True
                base_response["ngram_buckets"] = self.ngram_service.run(
                    prepared.texts,
                    top_n=self.config.top_ngrams_per_bucket,
                )
                return base_response

            if model_key == "bertopic":
                model_result = self.bertopic_service.run(
                    prepared.texts,
                    top_terms=self.config.top_terms_per_group,
                    language=self.config.bertopic_language,
                )
            else:
                embeddings = None
                embeddings = self.embedding_service.encode(
                    prepared.texts,
                    model_name=self.config.embedding_model,
                )
                if model_key == "kmeans":
                    model_result = self.kmeans_service.run(
                        embeddings,
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
            base_response["warnings"] = warnings
            base_response["groups"] = self._build_groups(
                documents=prepared.documents,
                assignments=[int(value) for value in model_result.get("assignments", [])],
                explicit_groups=model_result.get("groups", {}),
                model_key=model_key,
            )
            if model_key == "kmeans" and embeddings is not None:
                base_response["scatter_points"] = self._build_scatter_points(
                    documents=prepared.documents,
                    assignments=[int(value) for value in model_result.get("assignments", [])],
                    embeddings=embeddings,
                    groups=base_response["groups"],
                )
            base_response["ok"] = True
            return base_response
        except (TopicAnalysisInputError, TopicAnalysisDependencyError) as exc:
            base_response["error"] = str(exc)
            return base_response
        except Exception as exc:  # pragma: no cover - defensive guard
            base_response["error"] = f"Analysis failed unexpectedly: {exc}"
            return base_response

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
            if not terms:
                terms = self.keyword_service.top_terms(
                    grouped_texts,
                    top_n=self.config.top_terms_per_group,
                )

            is_noise = bool(explicit_group.get("is_noise", group_id == -1))
            fallback_prefix = "Theme" if model_key == "bertopic" else "Group"
            label = self.narrative_service.build_label(
                texts=grouped_texts,
                terms=terms,
                is_noise=is_noise,
                fallback_prefix=fallback_prefix,
                fallback_id=group_key,
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
                    "comment": comment,
                    "count": int(len(grouped_rows)),
                    "share": round(len(grouped_rows) / total_documents, 4),
                    "terms": terms,
                    "examples": examples,
                    "is_noise": is_noise,
                }
            )

        return groups

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

        if embedding_array.shape[1] >= 2 and embedding_array.shape[0] >= 2:
            projected = PCA(n_components=2, random_state=self.config.kmeans_random_state).fit_transform(embedding_array)
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
