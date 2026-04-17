from __future__ import annotations

import re

import pandas as pd

from app.core.exceptions import TopicAnalysisInputError
from app.services.language_normalization_service import EnglishTranslationService
from app.services.topic_analysis_services.config import (
    PreparedDocument,
    PreparedTextDataset,
)


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
