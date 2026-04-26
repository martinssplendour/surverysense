from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TopicAnalysisConfig:
    embedding_provider: str
    embedding_model: str
    embedding_api_key: str
    embedding_dimensions: int
    embedding_batch_size: int
    embedding_timeout_seconds: int
    community_similarity_threshold: float
    community_max_neighbors: int
    top_terms_per_group: int
    top_ngrams_per_bucket: int
    representative_examples_per_group: int
    max_document_chars: int
    embedding_fallback_provider: str = ""
    embedding_fallback_model: str = ""
    embedding_fallback_api_key: str = ""
    community_resolution: float = 1.0
    community_mutual_neighbors: bool = True


@dataclass(slots=True)
class PreparedDocument:
    row_number: int
    text: str
    source_text: str
    original_text: str
    translated_to_english: bool = False
    detected_language: str | None = None


@dataclass(slots=True)
class PreparedTextDataset:
    documents: list[PreparedDocument]
    total_row_count: int
    original_response_count: int
    skipped_row_count: int
    translated_document_count: int
    warnings: list[str]

    @property
    def texts(self) -> list[str]:
        return [document.text for document in self.documents]

    @property
    def unique_document_count(self) -> int:
        return len({document.text.casefold() for document in self.documents})
