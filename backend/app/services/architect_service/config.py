from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


DEFAULT_NULL_EQUIVALENTS = ["", "n/a", "na", "none", "null", ".", "-", "<na>", "nan"]
IDENTIFIER_VALUE_PATTERN = re.compile(r"^[0-9a-f]{6,}(?:-[0-9a-f]{2,}){2,}$", re.IGNORECASE)


@dataclass(slots=True)
class ManifestArchitectConfig:
    gemini_api_key: str
    gemini_model: str
    gemini_temperature: float
    gemini_timeout_seconds: int
    row_limit: int


class DiagnosticMode(str, Enum):
    AI = "ai"
    RULE_BASED = "rule_based"
