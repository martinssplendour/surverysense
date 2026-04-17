from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TopicAnalysisConfig:
    embedding_model: str
    embedding_local_path: str
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
