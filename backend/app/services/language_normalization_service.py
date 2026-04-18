"""Translates survey responses to English with explicit language detection and in-process caching."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.services.language_detection_service import LanguageDetectionService
from app.services.translation_gateway_service import (
    DeepTranslatorError,
    TranslationGatewayService,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class EnglishTranslationConfig:
    enabled: bool
    source_language: str
    target_language: str
    batch_size: int


@dataclass(slots=True)
class EnglishTranslationBatchResult:
    texts: list[str]
    translated_flags: list[bool]
    detected_languages: list[str | None]
    warnings: list[str]
    translated_count: int


@dataclass(slots=True)
class _TranslationCacheEntry:
    translated_text: str
    translated: bool
    detected_language: str | None


class EnglishTranslationService:
    """Detects the source language for each text, then translates non-English texts to English."""

    def __init__(self, *, config: EnglishTranslationConfig) -> None:
        self.config = config
        self._translation_cache: dict[str, _TranslationCacheEntry] = {}
        self.language_detection_service = LanguageDetectionService(
            source_language=config.source_language,
        )
        self.translation_gateway = TranslationGatewayService(
            target_language=config.target_language,
        )

    def warm_up(self) -> None:
        return

    def translate(self, texts: list[str]) -> EnglishTranslationBatchResult:
        """Translate a batch of texts to English, returning original texts if translation is disabled or fails."""
        passthrough = self._build_passthrough_result(texts)
        if not self.config.enabled or not texts:
            return passthrough

        warnings: list[str] = []
        unique_texts = list(dict.fromkeys(texts))
        pending_texts = [text for text in unique_texts if text not in self._translation_cache]

        if pending_texts:
            try:
                entries = self._translate_pending_texts(pending_texts, warnings)
            except ImportError as exc:
                logger.warning(
                    "English translation is unavailable because language detection is not installed (%s). Translation will be skipped for this request.",
                    type(exc).__name__,
                )
                warnings.append(
                    "English translation is unavailable because language detection is not installed. Reinstall backend requirements to enable translate-to-English features."
                )
                return self._build_passthrough_result(texts, warnings=warnings)
            self._translation_cache.update(entries)

        return self._finalize_result(texts, warnings=warnings)

    def _translate_pending_texts(
        self,
        pending_texts: list[str],
        warnings: list[str],
    ) -> dict[str, _TranslationCacheEntry]:
        grouped_texts: dict[str, list[str]] = {}
        detection_fallback_count = 0
        failed_count = 0

        for text in pending_texts:
            detected_language = self._detect_language(text)
            if not detected_language:
                detection_fallback_count += 1
                detected_language = self._normalize_source_language(self.config.source_language)
            grouped_texts.setdefault(detected_language, []).append(text)

        translated_entries: dict[str, _TranslationCacheEntry] = {}
        batch_size = max(1, self.config.batch_size)

        for source_language, source_texts in grouped_texts.items():
            if source_language == self.config.target_language:
                for text in source_texts:
                    translated_entries[text] = _TranslationCacheEntry(
                        translated_text=text,
                        translated=False,
                        detected_language=source_language,
                    )
                continue

            try:
                translator = self._get_translator(source_language)
            except (ImportError, DeepTranslatorError) as exc:
                logger.warning(
                    "English translation is unavailable for source_language=%s (%s). The original text will be kept.",
                    source_language,
                    type(exc).__name__,
                )
                for text in source_texts:
                    translated_entries[text] = _TranslationCacheEntry(
                        translated_text=text,
                        translated=False,
                        detected_language=source_language,
                    )
                continue

            for batch_start in range(0, len(source_texts), batch_size):
                batch = source_texts[batch_start: batch_start + batch_size]
                try:
                    translated_batch = self._translate_batch(translator, batch)
                except DeepTranslatorError as exc:
                    logger.warning(
                        "Batch translation failed for source_language=%s batch_size=%s (%s). Falling back to single-item translation.",
                        source_language,
                        len(batch),
                        type(exc).__name__,
                    )
                    translated_batch = []
                    for text in batch:
                        try:
                            translated_batch.append(self._translate_single(translator, text))
                        except DeepTranslatorError as single_exc:
                            logger.warning(
                                "Single-item translation failed for source_language=%s (%s). The original text will be kept for that response.",
                                source_language,
                                type(single_exc).__name__,
                            )
                            failed_count += 1
                            translated_batch.append(text)

                for source_text, translated_text in zip(batch, translated_batch):
                    normalized_text = self._normalize_translated_text(source_text, translated_text)
                    translated_entries[source_text] = _TranslationCacheEntry(
                        translated_text=normalized_text,
                        translated=normalized_text.casefold() != source_text.casefold(),
                        detected_language=source_language,
                    )

        if detection_fallback_count:
            warnings.append(
                f"Language detection fell back to the configured source language for {detection_fallback_count} response(s)."
            )
        if failed_count:
            warnings.append(
                f"Google Translate failed for {failed_count} response(s); analysis continued with the original text."
            )

        return translated_entries

    def _finalize_result(
        self,
        texts: list[str],
        *,
        warnings: list[str],
    ) -> EnglishTranslationBatchResult:
        translated_texts: list[str] = []
        translated_flags: list[bool] = []
        detected_languages: list[str | None] = []

        for text in texts:
            cached = self._translation_cache.get(
                text,
                _TranslationCacheEntry(
                    translated_text=text,
                    translated=False,
                    detected_language=None,
                ),
            )
            translated_texts.append(cached.translated_text)
            translated_flags.append(cached.translated)
            detected_languages.append(cached.detected_language)

        translated_count = sum(1 for translated in translated_flags if translated)
        return EnglishTranslationBatchResult(
            texts=translated_texts,
            translated_flags=translated_flags,
            detected_languages=detected_languages,
            warnings=warnings,
            translated_count=translated_count,
        )

    @staticmethod
    def _build_passthrough_result(
        texts: list[str],
        *,
        warnings: list[str] | None = None,
    ) -> EnglishTranslationBatchResult:
        return EnglishTranslationBatchResult(
            texts=list(texts),
            translated_flags=[False] * len(texts),
            detected_languages=[None] * len(texts),
            warnings=list(warnings or []),
            translated_count=0,
        )

    def _get_translator(self, source_language: str):
        return self.translation_gateway.get_translator(source_language)

    def _detect_language(self, text: str) -> str | None:
        return self.language_detection_service.detect_language(text)

    @staticmethod
    def _normalize_source_language(language: str) -> str:
        return LanguageDetectionService.normalize_source_language(language)

    @staticmethod
    def _translate_batch(translator, texts: list[str]) -> list[str]:
        return TranslationGatewayService.translate_batch(translator, texts)

    @staticmethod
    def _translate_single(translator, text: str) -> str:
        return TranslationGatewayService.translate_single(translator, text)

    @staticmethod
    def _normalize_translated_text(source_text: str, translated_text: str) -> str:
        return TranslationGatewayService.normalize_translated_text(source_text, translated_text)
