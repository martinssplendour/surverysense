"""Detects the character encoding of a raw CSV byte payload using a priority-ordered strategy chain."""
from __future__ import annotations

from dataclasses import dataclass

from app.core.exceptions import CsvDecodeError

try:
    import chardet
except ImportError:  # pragma: no cover - exercised implicitly in this environment.
    chardet = None


@dataclass(slots=True)
class EncodingDetectionResult:
    encoding: str
    strategy: str


class EncodingDetectionService:
    """Detects CSV encoding by trying UTF-8 first, then chardet, then legacy Windows fallbacks."""

    def detect(self, payload: bytes) -> EncodingDetectionResult:
        """Return the first encoding that successfully decodes the payload, or raise CsvDecodeError.

        Strategy order: utf-8-sig (BOM), utf-8, chardet heuristic, cp1252, latin-1.
        """
        for encoding in ("utf-8-sig", "utf-8"):
            if self._can_decode(payload, encoding):
                return EncodingDetectionResult(encoding=encoding, strategy="utf-8-first")

        if chardet is not None:
            detected = chardet.detect(payload)
            detected_encoding = str(detected.get("encoding") or "").strip()
            if detected_encoding and self._can_decode(payload, detected_encoding):
                return EncodingDetectionResult(encoding=detected_encoding, strategy="chardet")

        for fallback in ("cp1252", "latin-1"):
            if self._can_decode(payload, fallback):
                return EncodingDetectionResult(encoding=fallback, strategy="fallback")

        raise CsvDecodeError("Unable to detect a valid encoding for the uploaded CSV.")

    @staticmethod
    def _can_decode(payload: bytes, encoding: str) -> bool:
        try:
            payload.decode(encoding)
            return True
        except UnicodeDecodeError:
            return False
