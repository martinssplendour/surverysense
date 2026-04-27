from __future__ import annotations

import json
import logging
import re
import urllib.request
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SingleWordValidationConfig:
    enabled: bool
    gemini_api_key: str
    gemini_model: str
    timeout_seconds: int
    batch_size: int = 100


@dataclass(slots=True)
class SingleWordValidationResult:
    drop_words: set[str]
    warnings: list[str]
    checked_word_count: int


class GeminiSingleWordResponseValidationService:
    """Classifies one-word survey responses as keep/delete before topic analysis."""

    WORD_PATTERN = re.compile(r"\b[\w']+\b", re.UNICODE)

    def __init__(self, *, config: SingleWordValidationConfig) -> None:
        self.config = config
        self._decision_cache: dict[str, bool] = {}

    def is_available(self) -> bool:
        return bool(self.config.enabled and self.config.gemini_api_key.strip())

    def classify(self, words: list[str]) -> SingleWordValidationResult:
        normalized_words = self._normalize_words(words)
        if not normalized_words or not self.is_available():
            return SingleWordValidationResult(drop_words=set(), warnings=[], checked_word_count=0)

        pending_words = [word for word in normalized_words if word not in self._decision_cache]
        warnings: list[str] = []
        if pending_words:
            try:
                for batch in self._iter_batches(pending_words):
                    self._decision_cache.update(self._request_decisions(batch))
            except Exception as exc:
                logger.warning(
                    "Single-word response validation was skipped after Gemini failed (%s: %s).",
                    type(exc).__name__,
                    exc,
                )
                warnings.append(
                    "Single-word response validation was skipped because Gemini was unavailable; those responses were kept."
                )

        return SingleWordValidationResult(
            drop_words={word for word in normalized_words if self._decision_cache.get(word) is False},
            warnings=warnings,
            checked_word_count=len(normalized_words),
        )

    def _request_decisions(self, words: list[str]) -> dict[str, bool]:
        response_json = self._request_gemini(words)
        response_text = self._extract_gemini_text(response_json)
        if not response_text:
            raise ValueError("Gemini returned an empty single-word validation response.")

        payload = json.loads(response_text)
        if not isinstance(payload, dict):
            raise ValueError("Gemini single-word validation response was not a JSON object.")

        requested_words = set(words)
        decisions = {word: True for word in words}
        for item in payload.get("decisions", []):
            if not isinstance(item, dict):
                continue
            word = self.normalize_word(str(item.get("word", "")))
            if word not in requested_words:
                continue
            action = str(item.get("action", "")).strip().casefold()
            if action == "delete":
                decisions[word] = False
            elif action == "keep":
                decisions[word] = True
        return decisions

    def _request_gemini(self, words: list[str]) -> dict[str, Any]:
        endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.config.gemini_model}:generateContent"
        )
        request_payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": self._build_prompt(words)}],
                }
            ],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseSchema": self._response_schema(),
            },
        }
        payload = json.dumps(request_payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.config.gemini_api_key,
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Gemini did not return a JSON object.")
        return payload

    @staticmethod
    def _build_prompt(words: list[str]) -> str:
        evidence_blob = json.dumps({"words": words}, ensure_ascii=False, separators=(",", ":"))
        return (
            "You classify one-word survey responses before topic analysis.\n"
            "Return one decision for every input word.\n\n"
            "Rules:\n"
            "- action='keep' for valid English words, meaningful education/product/technical terms, known acronyms, "
            "or anything that could be genuine feedback.\n"
            "- action='delete' only for obvious junk: random letters, keyboard mashing, repeated-character noise, "
            "placeholder/test entries, or strings that are clearly not meaningful responses.\n"
            "- If uncertain, choose keep.\n"
            "- Do not add words that were not in the input.\n"
            "- Return JSON only.\n\n"
            f"Evidence:{evidence_blob}"
        )

    @staticmethod
    def _response_schema() -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "decisions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "word": {"type": "string"},
                            "action": {"type": "string", "enum": ["keep", "delete"]},
                        },
                        "required": ["word", "action"],
                    },
                }
            },
            "required": ["decisions"],
        }

    @staticmethod
    def _extract_gemini_text(response_json: dict[str, Any]) -> str:
        candidates = response_json.get("candidates", [])
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        text_parts = [str(part.get("text", "")) for part in parts if str(part.get("text", "")).strip()]
        return "\n".join(text_parts).strip()

    def _iter_batches(self, words: list[str]) -> list[list[str]]:
        batch_size = max(1, int(self.config.batch_size or 1))
        return [words[index : index + batch_size] for index in range(0, len(words), batch_size)]

    @classmethod
    def _normalize_words(cls, words: list[str]) -> list[str]:
        normalized_words: list[str] = []
        seen: set[str] = set()
        for word in words:
            normalized = cls.normalize_word(word)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            normalized_words.append(normalized)
        return normalized_words

    @classmethod
    def normalize_word(cls, word: str) -> str:
        tokens = [
            token.strip("_'").casefold()
            for token in cls.WORD_PATTERN.findall(str(word or ""))
            if token.strip("_'")
        ]
        if len(tokens) != 1:
            return ""
        return tokens[0]
