from __future__ import annotations

import logging

import pandas as pd

from app.features.ingestion.architect_service.config import (
    DEFAULT_NULL_EQUIVALENTS,
    ManifestArchitectConfig,
)
from app.features.ingestion.architect_service.manifest_column_stats_service import ManifestColumnStatsService
from app.features.ingestion.architect_service.manifest_header_scoring_service import ManifestHeaderScoringService
from app.features.ingestion.architect_service.vertical_layout_detection_service import VerticalLayoutDetectionService
from app.features.ingestion.architect_service.wide_verbatim_detection_service import WideVerbatimDetectionService
from app.models.manifest import LayoutState, TransformationManifest

logger = logging.getLogger(__name__)


class HeuristicManifestDiagnosisService:
    def __init__(self, config: ManifestArchitectConfig) -> None:
        self.config = config
        self.scoring_service = ManifestHeaderScoringService()
        self.column_stats_service = ManifestColumnStatsService(scoring_service=self.scoring_service)
        self.vertical_layout_service = VerticalLayoutDetectionService(
            column_stats_service=self.column_stats_service,
            scoring_service=self.scoring_service,
        )
        self.wide_verbatim_service = WideVerbatimDetectionService(
            scoring_service=self.scoring_service,
        )

    def build_manifest(
        self,
        df_sample: pd.DataFrame,
        column_index_map: dict[int, str],
    ) -> TransformationManifest:
        vertical_candidate = self.detect_vertical_layout(df_sample)
        if vertical_candidate is not None:
            manifest = TransformationManifest(
                diagnostic_source="heuristic",
                layout_state=LayoutState.VERTICAL,
                metadata_indices=vertical_candidate["metadata_indices"],
                verbatim_indices=[],
                vertical_assembly={
                    "is_required": True,
                    "record_key_indices": vertical_candidate["record_key_indices"],
                    "question_header_indices": vertical_candidate["question_header_indices"],
                    "answer_col_idx": vertical_candidate["answer_col_idx"],
                    "helper_indices": vertical_candidate["helper_indices"],
                    "duplicate_resolution": "last_non_null",
                    "row_consolidation": "one_row_per_record",
                },
                null_equivalents=DEFAULT_NULL_EQUIVALENTS,
                row_limit=self.config.row_limit,
                notes=[
                    "Manifest generated using rule-based diagnosis.",
                    "Vertical layout detected from repeated respondent/question patterns.",
                ],
            )
            logger.info(
                "Rule-based diagnosis completed with layout=%s source=%s metadata_columns=%s question_headers=%s.",
                manifest.layout_state,
                manifest.diagnostic_source,
                len(manifest.metadata_indices),
                len(manifest.vertical_assembly.question_header_indices),
            )
            return manifest

        verbatim_indices = self.detect_wide_verbatim_indices(df_sample)
        metadata_indices = [idx for idx in column_index_map if idx not in set(verbatim_indices)]
        manifest = TransformationManifest(
            diagnostic_source="heuristic",
            layout_state=LayoutState.WIDE,
            metadata_indices=metadata_indices,
            verbatim_indices=verbatim_indices,
            vertical_assembly={"is_required": False},
            null_equivalents=DEFAULT_NULL_EQUIVALENTS,
            row_limit=self.config.row_limit,
            notes=[
                "Manifest generated using rule-based diagnosis.",
                "Wide layout assumed because no strong vertical verbatim signature was found.",
            ],
        )
        logger.info(
            "Rule-based diagnosis completed with layout=%s source=%s metadata_columns=%s verbatim_columns=%s.",
            manifest.layout_state,
            manifest.diagnostic_source,
            len(manifest.metadata_indices),
            len(manifest.verbatim_indices),
        )
        return manifest

    def precompute_column_stats(self, df_sample: pd.DataFrame):
        return self.column_stats_service.precompute_column_stats(df_sample)

    def select_vertical_candidates(self, col_stats, *, top_k: int):
        return self.column_stats_service.select_vertical_candidates(col_stats, top_k=top_k)

    def detect_vertical_layout(self, df_sample: pd.DataFrame):
        return self.vertical_layout_service.detect_vertical_layout(df_sample)

    def score_vertical_candidate(self, df_sample: pd.DataFrame, record_key_idx: int, question_idx: int, answer_idx: int, col_stats=None):
        return self.vertical_layout_service.score_vertical_candidate(
            df_sample,
            record_key_idx,
            question_idx,
            answer_idx,
            col_stats,
        )

    def detect_question_header_indices(self, df_sample: pd.DataFrame, *, primary_question_idx: int, exclude_indices: set[int], col_stats=None):
        return self.vertical_layout_service.detect_question_header_indices(
            df_sample,
            primary_question_idx=primary_question_idx,
            exclude_indices=exclude_indices,
            col_stats=col_stats,
        )

    def detect_helper_indices(self, df_sample: pd.DataFrame, *, exclude_indices: set[int]):
        return self.vertical_layout_service.detect_helper_indices(
            df_sample,
            exclude_indices=exclude_indices,
        )

    def detect_wide_verbatim_indices(self, df_sample: pd.DataFrame) -> list[int]:
        return self.wide_verbatim_service.detect_wide_verbatim_indices(df_sample)

    @staticmethod
    def score_wide_verbatim_column(series: pd.Series, header_name: str) -> float:
        return ManifestHeaderScoringService.score_wide_verbatim_column(series, header_name)

    @staticmethod
    def score_question_header_column(series: pd.Series, header_name: str) -> float:
        return ManifestHeaderScoringService.score_question_header_column(series, header_name)

    @staticmethod
    def question_header_name_score(header_name: str) -> float:
        return ManifestHeaderScoringService.question_header_name_score(header_name)

    @staticmethod
    def record_key_header_score(header_name: str) -> float:
        return ManifestHeaderScoringService.record_key_header_score(header_name)

    @staticmethod
    def answer_header_score(header_name: str) -> float:
        return ManifestHeaderScoringService.answer_header_score(header_name)

    @staticmethod
    def helper_header_penalty(header_name: str) -> float:
        return ManifestHeaderScoringService.helper_header_penalty(header_name)

    @staticmethod
    def header_tokens(header_name: str) -> set[str]:
        return ManifestHeaderScoringService.header_tokens(header_name)

    @staticmethod
    def identifier_like_ratio(series: pd.Series) -> float:
        return ManifestHeaderScoringService.identifier_like_ratio(series)

    @staticmethod
    def header_hint_score(header_name: str, tokens: set[str]) -> float:
        return ManifestHeaderScoringService.header_hint_score(header_name, tokens)
