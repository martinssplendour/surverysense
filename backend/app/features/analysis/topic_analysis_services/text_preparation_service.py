from __future__ import annotations

import re

import pandas as pd

from app.core.exceptions import TopicAnalysisInputError
from app.features.analysis.language_normalization_service import EnglishTranslationService
from app.features.analysis.topic_analysis_services.config import (
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
    COMMA_DELIMITER_PATTERN = re.compile(r"[^,]+,?")
    FULL_STOP_SENTENCE_PATTERN = re.compile(r"[^.]+\.")
    WORD_PATTERN = re.compile(r"\b[\w']+\b")
    CONTINUATION_START_WORDS = frozenset({"because", "but", "however", "so", "therefore", "still"})

    def __init__(
        self,
        *,
        max_document_chars: int,
        translation_service: EnglishTranslationService | None = None,
        input_translation_enabled: bool = True,
    ) -> None:
        self.max_document_chars = max(200, max_document_chars)
        self.translation_service = translation_service
        self.input_translation_enabled = bool(input_translation_enabled)

    def warm_up(self) -> None:
        if self.translation_service is not None:
            self.translation_service.warm_up()

    def prepare(self, dataframe: pd.DataFrame, *, text_column_name: str) -> PreparedTextDataset:
        if text_column_name not in dataframe.columns:
            raise TopicAnalysisInputError(f"Column '{text_column_name}' is not available in the analysis dataset.")

        raw_documents: list[tuple[int, str, str]] = []
        warnings: list[str] = []
        original_response_count = 0
        skipped_count = 0
        truncated_count = 0

        for row_index, raw_value in dataframe[text_column_name].items():
            normalized = self._normalize_value(raw_value)
            if not normalized:
                skipped_count += 1
                continue

            original_response_count += 1
            if len(normalized) > self.max_document_chars:
                normalized = normalized[: self.max_document_chars].rstrip()
                truncated_count += 1

            row_number = self._resolve_row_number(row_index)
            for sentence in self._sentencize_for_embedding(normalized):
                raw_documents.append((row_number, sentence, normalized))

        if skipped_count:
            warnings.append(f"Skipped {skipped_count} empty or NaN row(s) before analysis.")
        if truncated_count:
            warnings.append(
                f"Trimmed {truncated_count} long response(s) to {self.max_document_chars} characters to keep the analysis stable."
            )

        translated_document_count = 0
        if self.translation_service is not None and self.input_translation_enabled and raw_documents:
            source_texts = [text for _, text, _ in raw_documents]
            translation_result = self.translation_service.translate(source_texts)
            warnings.extend(translation_result.warnings)
            translated_document_count = translation_result.translated_count
            documents = [
                PreparedDocument(
                    row_number=row_number,
                    text=translated_text,
                    source_text=source_text,
                    original_text=original_text,
                    translated_to_english=translated,
                    detected_language=detected_language,
                )
                for (row_number, source_text, original_text), translated_text, translated, detected_language in zip(
                    raw_documents,
                    translation_result.texts,
                    translation_result.translated_flags,
                    translation_result.detected_languages,
                )
            ]
        else:
            detected_languages = [None] * len(raw_documents)
            if self.translation_service is not None and raw_documents:
                detection_result = self.translation_service.detect_languages([text for _, text, _ in raw_documents])
                warnings.extend(detection_result.warnings)
                detected_languages = detection_result.detected_languages
            documents = [
                PreparedDocument(
                    row_number=row_number,
                    text=normalized,
                    source_text=normalized,
                    original_text=original_text,
                    translated_to_english=False,
                    detected_language=detected_language,
                )
                for (row_number, normalized, original_text), detected_language in zip(raw_documents, detected_languages)
            ]

        return PreparedTextDataset(
            documents=documents,
            total_row_count=int(len(dataframe)),
            original_response_count=original_response_count,
            skipped_row_count=skipped_count,
            translated_document_count=translated_document_count,
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

    @classmethod
    def _sentencize_for_embedding(cls, text: str) -> list[str]:
        full_stop_sentences = [match.group(0).strip() for match in cls.FULL_STOP_SENTENCE_PATTERN.finditer(text)]
        if len(full_stop_sentences) >= 2 and cls._covers_text(full_stop_sentences, text):
            return cls._valid_sentence_chunks(full_stop_sentences) or [text]

        if "." in text:
            return [text]

        raw_sentences = [match.group(0).strip() for match in cls.COMMA_DELIMITER_PATTERN.finditer(text) if match.group(0).strip()]
        if len(raw_sentences) < 2:
            return [text]

        if not cls._covers_text(raw_sentences, text):
            return [text]

        sentences = [sentence[:-1].strip() if sentence.endswith(",") else sentence for sentence in raw_sentences]
        return cls._valid_sentence_chunks(sentences) or [text]

    @classmethod
    def _valid_sentence_chunks(cls, sentences: list[str]) -> list[str]:
        sentences = cls._merge_continuation_sentences(sentences)
        if len(sentences) < 2:
            return []
        if any(len(cls.WORD_PATTERN.findall(sentence)) <= 3 for sentence in sentences):
            return []
        return sentences

    @classmethod
    def _merge_continuation_sentences(cls, sentences: list[str]) -> list[str]:
        merged: list[str] = []
        for sentence in sentences:
            words = cls.WORD_PATTERN.findall(sentence.casefold())
            starts_with_continuation = bool(words and words[0] in cls.CONTINUATION_START_WORDS)
            if merged and starts_with_continuation:
                merged[-1] = f"{merged[-1]} {sentence}".strip()
            else:
                merged.append(sentence)
        return merged

    @classmethod
    def _covers_text(cls, sentences: list[str], text: str) -> bool:
        covered_text = " ".join(sentences)
        return cls.WHITESPACE_PATTERN.sub(" ", covered_text).strip() == cls.WHITESPACE_PATTERN.sub(" ", text).strip()

    @staticmethod
    def _resolve_row_number(row_index: object) -> int:
        if isinstance(row_index, int):
            return row_index + 1
        if isinstance(row_index, float) and row_index.is_integer():
            return int(row_index) + 1
        return 0
