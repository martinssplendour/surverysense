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
    def detect(self, payload: bytes) -> EncodingDetectionResult:
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
