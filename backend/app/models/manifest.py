from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class LayoutState(StrEnum):
    WIDE = "WIDE"
    VERTICAL = "VERTICAL"


class VerticalAssemblyPlan(BaseModel):
    is_required: bool = False
    record_key_indices: list[int] = Field(default_factory=list)
    question_header_indices: list[int] = Field(default_factory=list)
    answer_col_idx: int = -1
    helper_indices: list[int] = Field(default_factory=list)
    duplicate_resolution: Literal["last_non_null"] = "last_non_null"
    row_consolidation: Literal["one_row_per_record"] = "one_row_per_record"

    @property
    def resolved_answer_col_idx(self) -> int | None:
        return None if self.answer_col_idx < 0 else self.answer_col_idx


class TransformationManifest(BaseModel):
    diagnostic_source: Literal["gemini", "heuristic"] = "heuristic"
    layout_state: LayoutState
    metadata_indices: list[int] = Field(default_factory=list)
    verbatim_indices: list[int] = Field(default_factory=list)
    vertical_assembly: VerticalAssemblyPlan = Field(default_factory=VerticalAssemblyPlan)
    null_equivalents: list[str] = Field(
        default_factory=lambda: ["", "n/a", "na", "none", "null", ".", "-", "<na>", "nan"]
    )
    row_limit: int = 5000
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_manifest(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value

        if "vertical_assembly" in value:
            return value

        legacy = dict(value)
        pivot_logic = legacy.pop("pivot_logic", None)
        if isinstance(pivot_logic, dict):
            legacy["vertical_assembly"] = {
                "is_required": bool(pivot_logic.get("is_required", False)),
                "record_key_indices": pivot_logic.get("index_col_indices", []),
                "question_header_indices": [
                    pivot_logic.get("question_col_idx", -1),
                ] if int(pivot_logic.get("question_col_idx", -1)) >= 0 else [],
                "answer_col_idx": pivot_logic.get("answer_col_idx", -1),
                "duplicate_resolution": "last_non_null",
                "row_consolidation": "one_row_per_record",
            }
        return legacy

    @model_validator(mode="after")
    def validate_manifest(self) -> TransformationManifest:
        self.metadata_indices = _unique_non_negative(self.metadata_indices)
        self.verbatim_indices = _unique_non_negative(self.verbatim_indices)
        self.vertical_assembly.record_key_indices = _unique_non_negative(
            self.vertical_assembly.record_key_indices
        )
        self.vertical_assembly.question_header_indices = _unique_non_negative(
            self.vertical_assembly.question_header_indices
        )
        self.vertical_assembly.helper_indices = _unique_non_negative(
            self.vertical_assembly.helper_indices
        )
        self.null_equivalents = _unique_normalized_strings(self.null_equivalents)

        if self.row_limit <= 0:
            raise ValueError("row_limit must be a positive integer.")

        if self.layout_state == LayoutState.VERTICAL and self.vertical_assembly.is_required:
            if not self.vertical_assembly.record_key_indices:
                raise ValueError("record_key_indices are required for vertical layouts.")
            if not self.vertical_assembly.question_header_indices:
                raise ValueError("question_header_indices are required for vertical layouts.")
            if self.vertical_assembly.resolved_answer_col_idx is None:
                raise ValueError("answer_col_idx is required for vertical layouts.")

            overlapping = (
                set(self.vertical_assembly.record_key_indices)
                & set(self.vertical_assembly.question_header_indices)
            )
            if overlapping:
                raise ValueError("record_key_indices and question_header_indices must not overlap.")

            answer_idx = self.vertical_assembly.resolved_answer_col_idx
            if answer_idx in set(self.vertical_assembly.record_key_indices):
                raise ValueError("answer_col_idx must not overlap with record_key_indices.")
            if answer_idx in set(self.vertical_assembly.question_header_indices):
                raise ValueError("answer_col_idx must not overlap with question_header_indices.")

            self.metadata_indices = _unique_non_negative(
                self.metadata_indices + self.vertical_assembly.record_key_indices
            )

        return self


def _unique_non_negative(values: list[int]) -> list[int]:
    seen: set[int] = set()
    normalized_values: list[int] = []
    for value in values:
        normalized = int(value)
        if normalized < 0 or normalized in seen:
            continue
        seen.add(normalized)
        normalized_values.append(normalized)
    return normalized_values


def _unique_normalized_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized_values: list[str] = []
    for value in values:
        normalized = str(value).strip()
        token = normalized.casefold()
        if token in seen:
            continue
        seen.add(token)
        normalized_values.append(normalized)
    return normalized_values
