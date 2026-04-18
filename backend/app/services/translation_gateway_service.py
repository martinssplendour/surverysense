from __future__ import annotations

from threading import Lock

try:  # pragma: no cover - optional dependency at runtime
    from deep_translator.exceptions import BaseError as DeepTranslatorError
except ImportError:  # pragma: no cover - dependency may be absent until installed
    DeepTranslatorError = Exception


class TranslationGatewayService:
    def __init__(self, *, target_language: str) -> None:
        self.target_language = target_language
        self._lock = Lock()
        self._translators_by_source: dict[str, object] = {}

    def get_translator(self, source_language: str):
        with self._lock:
            if source_language not in self._translators_by_source:
                from deep_translator import GoogleTranslator

                self._translators_by_source[source_language] = GoogleTranslator(
                    source=source_language,
                    target=self.target_language,
                )
            return self._translators_by_source[source_language]

    @staticmethod
    def translate_batch(translator, texts: list[str]) -> list[str]:
        translated = translator.translate_batch(texts)
        if isinstance(translated, str):
            return [translated]
        return [str(item).strip() for item in translated]

    @staticmethod
    def translate_single(translator, text: str) -> str:
        translated = translator.translate(text)
        return str(translated).strip()

    @staticmethod
    def normalize_translated_text(source_text: str, translated_text: str) -> str:
        normalized = str(translated_text).strip()
        return normalized or source_text
