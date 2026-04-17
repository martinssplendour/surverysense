from __future__ import annotations

from dataclasses import dataclass
import logging
from threading import Lock


logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency at runtime
    from deep_translator.exceptions import BaseError as DeepTranslatorError
except ImportError:  # pragma: no cover - dependency may be absent until installed
    DeepTranslatorError = Exception


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
    def __init__(self, *, config: EnglishTranslationConfig) -> None:
        self.config = config
        self._lock = Lock()
        self._translation_cache: dict[str, _TranslationCacheEntry] = {}
        self._translator = None

    def warm_up(self) -> None:
        return

    def translate(self, texts: list[str]) -> EnglishTranslationBatchResult:
        passthrough = self._build_passthrough_result(texts)
        if not self.config.enabled or not texts:
            return passthrough

        warnings: list[str] = []
        unique_texts = list(dict.fromkeys(texts))
        pending_texts: list[str] = []

        for text in unique_texts:
            if text in self._translation_cache:
                continue
            pending_texts.append(text)

        if self.config.target_language == "en":
            for text in list(pending_texts):
                if self._is_latin_script(text):
                    self._translation_cache[text] = _TranslationCacheEntry(
                        translated_text=text,
                        translated=False,
                        detected_language="en",
                    )
                    pending_texts.remove(text)

        if pending_texts:
            try:
                translator = self._get_translator()
            except (ImportError, DeepTranslatorError) as exc:
                logger.warning(
                    "English normalisation translator unavailable (%s: %s).",
                    type(exc).__name__,
                    exc,
                )
                warnings.append(
                    "English normalisation is unavailable because deep-translator is not installed. Reinstall backend requirements to enable Google Translate before analysis."
                )
                return self._build_passthrough_result(texts, warnings=warnings)

            failed_count = 0
            batch_size = max(1, self.config.batch_size)
            for batch_start in range(0, len(pending_texts), batch_size):
                batch = pending_texts[batch_start: batch_start + batch_size]
                try:
                    translated_batch = self._translate_batch(translator, batch)
                except DeepTranslatorError as exc:
                    logger.warning(
                        "Batch translation failed (%s: %s); falling back to single-item translation.",
                        type(exc).__name__,
                        exc,
                    )
                    fallback_batch: list[str] = []
                    for text in batch:
                        try:
                            fallback_batch.append(self._translate_single(translator, text))
                        except DeepTranslatorError as single_exc:
                            logger.warning(
                                "Single-item translation failed (%s: %s).",
                                type(single_exc).__name__,
                                single_exc,
                            )
                            failed_count += 1
                            fallback_batch.append(text)
                    translated_batch = fallback_batch

                for source_text, translated_text in zip(batch, translated_batch):
                    normalized_text = self._normalize_translated_text(source_text, translated_text)
                    self._translation_cache[source_text] = _TranslationCacheEntry(
                        translated_text=normalized_text,
                        translated=normalized_text.casefold() != source_text.casefold(),
                        detected_language=None,
                    )

            if failed_count:
                warnings.append(
                    f"Google Translate failed for {failed_count} response(s); analysis continued with the original text."
                )

        return self._finalize_result(texts, warnings=warnings)

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
                _TranslationCacheEntry(translated_text=text, translated=False, detected_language=None),
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

    def _get_translator(self):
        with self._lock:
            if self._translator is None:
                from deep_translator import GoogleTranslator

                self._translator = GoogleTranslator(
                    source=self.config.source_language,
                    target=self.config.target_language,
                )
            return self._translator

    @staticmethod
    def _translate_batch(translator, texts: list[str]) -> list[str]:
        translated = translator.translate_batch(texts)
        if isinstance(translated, str):
            return [translated]
        return [str(item).strip() for item in translated]

    @staticmethod
    def _translate_single(translator, text: str) -> str:
        translated = translator.translate(text)
        return str(translated).strip()

    @staticmethod
    def _is_latin_script(text: str) -> bool:
        """Return True if the text is predominantly Latin-script (ASCII alphabetic chars).
        Used to skip the Google Translate API for texts that are already English.
        Non-Latin scripts (Cyrillic, Arabic, CJK, Devanagari, etc.) have a low ASCII
        alphabetic ratio and will still be sent for translation."""
        alpha_chars = [c for c in text if c.isalpha()]
        if not alpha_chars:
            return True
        ascii_alpha = sum(1 for c in alpha_chars if ord(c) < 128)
        return ascii_alpha / len(alpha_chars) >= 0.85

    @staticmethod
    def _normalize_translated_text(source_text: str, translated_text: str) -> str:
        normalized = str(translated_text).strip()
        return normalized or source_text
