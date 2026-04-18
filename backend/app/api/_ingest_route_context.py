from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, status

from app.models.api import (
    MetadataFilterDefinitionModel,
    MetadataFilterOptionModel,
)
from app.services.architect_service import ManifestArchitectService
from app.services.cleaning_services import AnalysisReadyDatasetService
from app.services.csv_ingestion_service import CsvIngestionService
from app.services.language_normalization_service import EnglishTranslationService
from app.services.report_export_service import AnalysisReportExportService
from app.services.result_store_service import ResultStoreService
from app.services.topic_analysis_services import TopicAnalysisService
from app.services.transformation_service import DataTransformationService


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class IngestRouteContext:
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

    def raise_unexpected_api_error(self, action: str, exc: Exception) -> None:
        logger.exception("API action '%s' failed unexpectedly.", action)
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
