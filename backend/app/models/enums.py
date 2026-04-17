"""Shared enumerations used across models and services."""
from __future__ import annotations

from enum import StrEnum


class ColumnRole(StrEnum):
    """Whether a transformed column should be treated as metadata or as an open-text verbatim answer."""

    METADATA = "metadata"
    VERBATIM = "verbatim"
