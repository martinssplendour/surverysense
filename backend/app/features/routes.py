"""Workspace router factory composed from feature-owned endpoint modules."""
from __future__ import annotations

from fastapi import APIRouter

from app.features.analysis.language_normalization_service import EnglishTranslationService
from app.features.analysis.routes import register_analysis_routes
from app.features.analysis.topic_analysis_services import TopicAnalysisService
from app.features.analysis.translation_routes import register_translation_routes
from app.features.common.route_context import WorkspaceRouteContext
from app.features.export.report_export_service import AnalysisReportExportService
from app.features.ingestion.architect_service import ManifestArchitectService
from app.features.ingestion.cleaning_services import AnalysisReadyDatasetService
from app.features.ingestion.csv_ingestion_service import CsvIngestionService
from app.features.ingestion.routes import register_upload_routes
from app.features.ingestion.transformation_service import DataTransformationService
from app.features.results.routes import register_result_routes
from app.features.results.store import ResultStoreService


def build_workspace_router(
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
    """Build and return the APIRouter containing upload, analysis, and result endpoints."""
    context = WorkspaceRouteContext(
        router=APIRouter(tags=["workspace"]),
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
