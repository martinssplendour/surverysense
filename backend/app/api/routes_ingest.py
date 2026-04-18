"""Ingest router factory split across focused endpoint-registration modules."""
from __future__ import annotations

from fastapi import APIRouter

from app.api._ingest_analysis_routes import register_analysis_routes
from app.api._ingest_result_routes import register_result_routes
from app.api._ingest_route_context import IngestRouteContext
from app.api._ingest_translation_routes import register_translation_routes
from app.api._ingest_upload_routes import register_upload_routes
from app.services.architect_service import ManifestArchitectService
from app.services.cleaning_services import AnalysisReadyDatasetService
from app.services.csv_ingestion_service import CsvIngestionService
from app.services.language_normalization_service import EnglishTranslationService
from app.services.report_export_service import AnalysisReportExportService
from app.services.result_store_service import ResultStoreService
from app.services.topic_analysis_services import TopicAnalysisService
from app.services.transformation_service import DataTransformationService


def build_ingest_router(
    ingestion_service: CsvIngestionService,
    architect_service: ManifestArchitectService,
    transformation_service: DataTransformationService,
    analysis_ready_service: AnalysisReadyDatasetService,
    topic_analysis_service: TopicAnalysisService,
    report_export_service: AnalysisReportExportService,
    result_store_service: ResultStoreService,
    translation_service: EnglishTranslationService,
    architect_sample_size: int,
) -> APIRouter:
    """Build and return the APIRouter containing all ingest/analysis endpoints."""
    context = IngestRouteContext(
        router=APIRouter(tags=["ingestion"]),
        ingestion_service=ingestion_service,
        architect_service=architect_service,
        transformation_service=transformation_service,
        analysis_ready_service=analysis_ready_service,
        topic_analysis_service=topic_analysis_service,
        report_export_service=report_export_service,
        result_store_service=result_store_service,
        translation_service=translation_service,
        architect_sample_size=architect_sample_size,
    )

    register_upload_routes(context)
    register_analysis_routes(context)
    register_result_routes(context)
    register_translation_routes(context)
    return context.router
