"""Builds a TransformationManifest from a CSV sample, using Gemini AI or rule-based heuristics."""
from __future__ import annotations

import logging

import pandas as pd

from app.core.exceptions import ManifestBuildError
from app.models.manifest import TransformationManifest
from app.features.ingestion.architect_service.config import (
    DiagnosticMode,
    ManifestArchitectConfig,
)
from app.features.ingestion.architect_service.gemini_manifest_diagnosis_service import (
    GeminiManifestDiagnosisService,
)
from app.features.ingestion.architect_service.heuristic_manifest_diagnosis_service import (
    HeuristicManifestDiagnosisService,
)

logger = logging.getLogger(__name__)


class ManifestArchitectService:
    """Diagnoses a survey CSV sample and produces a TransformationManifest describing its layout and columns."""

    def __init__(self, config: ManifestArchitectConfig) -> None:
        self.config = config
        self.gemini_diagnosis_service = GeminiManifestDiagnosisService(config)
        self.heuristic_diagnosis_service = HeuristicManifestDiagnosisService(config)

    def is_ai_available(self) -> bool:
        return bool(self.config.gemini_api_key)

    def default_diagnostic_mode(self) -> DiagnosticMode:
        return DiagnosticMode.AI if self.is_ai_available() else DiagnosticMode.RULE_BASED

    def get_transformation_manifest(
        self,
        df_sample: pd.DataFrame,
        column_index_map: dict[int, str],
        *,
        diagnostic_mode: DiagnosticMode | None = None,
    ) -> TransformationManifest:
        mode = diagnostic_mode or self.default_diagnostic_mode()
        logger.info(
            "Transformation manifest build started with mode=%s sampled_rows=%s sampled_columns=%s.",
            "AI diagnosis" if mode == DiagnosticMode.AI else "rule-based diagnosis",
            len(df_sample),
            len(column_index_map),
        )
        if mode == DiagnosticMode.AI:
            if not self.is_ai_available():
                raise ManifestBuildError(
                    "AI diagnosis is not configured on this server. Add GEMINI_API_KEY or switch to rule-based diagnosis."
                )
            try:
                return self._build_manifest_with_gemini(df_sample, column_index_map)
            except Exception as exc:
                logger.warning(
                    "AI diagnosis failed during manifest build (%s). Falling back to rule-based diagnosis.",
                    type(exc).__name__,
                )
                manifest = self._build_manifest_heuristically(df_sample, column_index_map)
                manifest.notes.append(
                    f"AI diagnosis failed â€” rule-based fallback used. Reason: {exc}"
                )
                return manifest
        return self._build_manifest_heuristically(df_sample, column_index_map)

    def _build_manifest_with_gemini(
        self,
        df_sample: pd.DataFrame,
        column_index_map: dict[int, str],
    ) -> TransformationManifest:
        return self.gemini_diagnosis_service.build_manifest(df_sample, column_index_map)

    def _build_manifest_heuristically(
        self,
        df_sample: pd.DataFrame,
        column_index_map: dict[int, str],
    ) -> TransformationManifest:
        return self.heuristic_diagnosis_service.build_manifest(df_sample, column_index_map)

    def _build_gemini_prompt(
        self,
        df_sample: pd.DataFrame,
        column_index_map: dict[int, str],
    ) -> str:
        return self.gemini_diagnosis_service.build_prompt(df_sample, column_index_map)

    @staticmethod
    def _gemini_response_schema():
        return GeminiManifestDiagnosisService.response_schema()

    @staticmethod
    def _extract_gemini_text(response_json):
        return GeminiManifestDiagnosisService.extract_text(response_json)

    @staticmethod
    def _serialize_rows(df_sample: pd.DataFrame):
        return GeminiManifestDiagnosisService.serialize_rows(df_sample)

    def _precompute_column_stats(self, df_sample: pd.DataFrame):
        return self.heuristic_diagnosis_service.precompute_column_stats(df_sample)

    def _select_vertical_candidates(self, col_stats, *, top_k: int):
        return self.heuristic_diagnosis_service.select_vertical_candidates(col_stats, top_k=top_k)

    def _detect_vertical_layout(self, df_sample: pd.DataFrame):
        return self.heuristic_diagnosis_service.detect_vertical_layout(df_sample)

    def _score_vertical_candidate(
        self,
        df_sample: pd.DataFrame,
        record_key_idx: int,
        question_idx: int,
        answer_idx: int,
        col_stats=None,
    ):
        return self.heuristic_diagnosis_service.score_vertical_candidate(
            df_sample,
            record_key_idx,
            question_idx,
            answer_idx,
            col_stats,
        )

    def _detect_question_header_indices(
        self,
        df_sample: pd.DataFrame,
        *,
        primary_question_idx: int,
        exclude_indices: set[int],
        col_stats=None,
    ):
        return self.heuristic_diagnosis_service.detect_question_header_indices(
            df_sample,
            primary_question_idx=primary_question_idx,
            exclude_indices=exclude_indices,
            col_stats=col_stats,
        )

    def _detect_helper_indices(self, df_sample: pd.DataFrame, *, exclude_indices: set[int]):
        return self.heuristic_diagnosis_service.detect_helper_indices(df_sample, exclude_indices=exclude_indices)

    def _detect_wide_verbatim_indices(self, df_sample: pd.DataFrame):
        return self.heuristic_diagnosis_service.detect_wide_verbatim_indices(df_sample)

    @staticmethod
    def _score_wide_verbatim_column(series, header_name: str) -> float:
        return HeuristicManifestDiagnosisService.score_wide_verbatim_column(series, header_name)

    @staticmethod
    def _score_question_header_column(series, header_name: str) -> float:
        return HeuristicManifestDiagnosisService.score_question_header_column(series, header_name)

    @staticmethod
    def _question_header_name_score(header_name: str) -> float:
        return HeuristicManifestDiagnosisService.question_header_name_score(header_name)

    @staticmethod
    def _record_key_header_score(header_name: str) -> float:
        return HeuristicManifestDiagnosisService.record_key_header_score(header_name)

    @staticmethod
    def _answer_header_score(header_name: str) -> float:
        return HeuristicManifestDiagnosisService.answer_header_score(header_name)

    @staticmethod
    def _helper_header_penalty(header_name: str) -> float:
        return HeuristicManifestDiagnosisService.helper_header_penalty(header_name)

    @staticmethod
    def _header_tokens(header_name: str) -> set[str]:
        return HeuristicManifestDiagnosisService.header_tokens(header_name)

    @staticmethod
    def _identifier_like_ratio(series) -> float:
        return HeuristicManifestDiagnosisService.identifier_like_ratio(series)

    @staticmethod
    def _header_hint_score(header_name: str, tokens: set[str]) -> float:
        return HeuristicManifestDiagnosisService.header_hint_score(header_name, tokens)
