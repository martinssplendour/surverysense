from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol

from app.models.api import AnalysisExportRequest
from app.models.enums import AnalysisModelKey
from app.features.analysis.language_normalization_service import EnglishTranslationBatchResult
from app.features.analysis.topic_analysis_services.contracts import (
    AnalysisGroupRecord,
    AnalysisRunResult,
)
from app.features.analysis.topic_label_ai_service import TopicAiLabelingBatchResult

if TYPE_CHECKING:
    from app.features.results.models import AnalysisNgramDocumentsPage


class TranslationServiceProtocol(Protocol):
    def warm_up(self) -> None: ...

    def translate(self, texts: list[str]) -> EnglishTranslationBatchResult: ...


class TopicLabelServiceProtocol(Protocol):
    def label_groups(
        self,
        groups: Sequence[AnalysisGroupRecord],
        *,
        model_key: AnalysisModelKey,
        text_column_name: str,
    ) -> TopicAiLabelingBatchResult: ...


class ResultStoreReportReaderProtocol(Protocol):
    def get_fast_filtered_result(
        self,
        result_id: str,
        *,
        model_key: AnalysisModelKey,
        text_column_name: str,
        filters: dict[str, list[str]] | None,
    ) -> AnalysisRunResult | None: ...

    def get_analysis_ngram_page(
        self,
        result_id: str,
        *,
        ngram_size: int,
        term: str,
        offset: int,
        limit: int,
    ) -> AnalysisNgramDocumentsPage: ...


class ReportContentServiceProtocol(Protocol):
    def build_summary_lines(self, request: AnalysisExportRequest) -> list[str]: ...
