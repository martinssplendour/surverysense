from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import NoReturn, TypeVar

from fastapi import APIRouter, HTTPException, status

from app.core.exceptions import IngestionError
from app.features.analysis.language_normalization_service import EnglishTranslationService
from app.features.analysis.topic_analysis_services import TopicAnalysisService
from app.features.export.report_export_service import AnalysisReportExportService
from app.features.ingestion.architect_service import ManifestArchitectService
from app.features.ingestion.cleaning_services import AnalysisReadyDatasetService
from app.features.ingestion.csv_ingestion_service import CsvIngestionService
from app.features.ingestion.transformation_service import DataTransformationService
from app.features.results.store import ResultNotFoundError, ResultStoreService
from app.models.api import (
    MetadataFilterDefinitionModel,
    MetadataFilterOptionModel,
)

logger = logging.getLogger(__name__)
_T = TypeVar("_T")


@dataclass(slots=True)
class WorkspaceRouteContext:
    router: APIRouter
    ingestion_service: CsvIngestionService
    architect_service: ManifestArchitectService
    transformation_service: DataTransformationService
    analysis_ready_service: AnalysisReadyDatasetService
    topic_analysis_service: TopicAnalysisService
    report_export_service: AnalysisReportExportService
    result_store_service: ResultStoreService
    translation_service: EnglishTranslationService
    architect_sample_size: int

    def execute_api_action(self, action: str, operation: Callable[[], _T]) -> _T:
        try:
            return operation()
        except HTTPException:
            raise
        except Exception as exc:
            self.raise_mapped_api_error(action, exc)

    def raise_mapped_api_error(self, action: str, exc: Exception) -> NoReturn:
        if isinstance(exc, ResultNotFoundError):
            logger.info("API action '%s' could not find result state: %s", action, exc)
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        if isinstance(exc, ValueError):
            logger.info("API action '%s' rejected invalid input: %s", action, exc)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        if isinstance(exc, IngestionError):
            logger.warning(
                "API action '%s' failed with a recoverable ingestion error (%s: %s).",
                action,
                type(exc).__name__,
                exc,
            )
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        self.raise_unexpected_api_error(action, exc)

    def raise_unexpected_api_error(self, action: str, exc: Exception) -> NoReturn:
        logger.exception(
            "API action '%s' failed unexpectedly (%s: %s).",
            action,
            type(exc).__name__,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred.",
        ) from exc

    def serialize_filters(self, result_id: str) -> list[MetadataFilterDefinitionModel]:
        definitions = self.result_store_service.get_filters(result_id)
        return [
            MetadataFilterDefinitionModel(
                column_name=definition.column_name,
                display_name=definition.display_name,
                options=[
                    MetadataFilterOptionModel(value=option.value, count=option.count)
                    for option in definition.options
                ],
            )
            for definition in definitions
        ]

    @staticmethod
    def parse_filters(raw_filters: str | None) -> dict[str, list[str]]:
        if raw_filters is None or not raw_filters.strip():
            return {}

        try:
            parsed = json.loads(raw_filters)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="filters must be valid JSON.",
            ) from exc

        if not isinstance(parsed, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="filters must be a JSON object keyed by column name.",
            )

        normalized: dict[str, list[str]] = {}
        for key, value in parsed.items():
            if not isinstance(key, str):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="filter column names must be strings.",
                )
            if isinstance(value, str):
                values = [value]
            elif isinstance(value, list):
                values = [item for item in value if isinstance(item, str)]
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"filter values for '{key}' must be a string or string array.",
                )
            normalized[key] = values
        return normalized
