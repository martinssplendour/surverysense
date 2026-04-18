from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency at runtime
    from langdetect import DetectorFactory, LangDetectException, detect

    DetectorFactory.seed = 0
except ImportError:  # pragma: no cover - dependency may be absent until installed
    LangDetectException = Exception
    detect = None


class LanguageDetectionService:
    def __init__(self, *, source_language: str) -> None:
        self.source_language = source_language

    def detect_language(self, text: str) -> str | None:
        if self.source_language != "auto":
            return self.normalize_source_language(self.source_language)
        if detect is None:
            raise ImportError("langdetect is not installed")

        try:
            detected_language = detect(text)
        except LangDetectException as exc:
            logger.warning(
                "Language detection failed (%s). Falling back to configured source=%s for this response.",
                type(exc).__name__,
                self.source_language,
            )
            return None
        return self.normalize_source_language(detected_language)

    @staticmethod
    def normalize_source_language(language: str) -> str:
        normalized = str(language or "").strip()
        if not normalized or normalized.casefold() == "auto":
            return "auto"

        language_map = {
            "zh-cn": "zh-CN",
            "zh-tw": "zh-TW",
            "pt-br": "pt",
        }
        return language_map.get(normalized.casefold(), normalized)
