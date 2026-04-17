from __future__ import annotations

from enum import StrEnum


class ColumnRole(StrEnum):
    METADATA = "metadata"
    VERBATIM = "verbatim"
