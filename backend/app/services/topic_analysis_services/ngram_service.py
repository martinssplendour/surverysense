from __future__ import annotations

from app.services.topic_analysis_services.config import PreparedDocument
from app.services.topic_analysis_services.keyword_service import TopicAnalysisKeywordService


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
