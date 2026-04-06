from __future__ import annotations

from fastapi import FastAPI

from app.api.routes_ingest import build_ingest_router
from app.core.settings import get_settings
from app.services.architect_service import ManifestArchitectConfig, ManifestArchitectService
from app.services.cleaning_services import (
    DuplicateAnswerResolutionService,
    MetadataConsolidationService,
    NullScrubbingService,
    QuestionHeaderResolutionService,
    TextNormalizationService,
    VerbatimHeaderCleaningService,
    VerbatimRowFilterService,
    VerticalRecordAssemblyService,
    VerticalRecordFilterService,
)
from app.services.csv_ingestion_service import CsvIngestionService
from app.services.encoding_service import EncodingDetectionService
from app.services.transformation_service import DataTransformationService


def create_app() -> FastAPI:
    settings = get_settings()

    ingestion_service = CsvIngestionService(
        encoding_service=EncodingDetectionService(),
        sample_size=settings.ingest_sample_size,
        architect_sample_size=settings.architect_sample_size,
    )
    architect_service = ManifestArchitectService(
        ManifestArchitectConfig(
            gemini_api_key=settings.gemini_api_key,
            gemini_model=settings.gemini_model,
            gemini_temperature=settings.gemini_temperature,
            gemini_timeout_seconds=settings.gemini_timeout_seconds,
            row_limit=settings.row_limit,
        )
    )
    text_normalizer = TextNormalizationService()
    transformation_service = DataTransformationService(
        text_normalizer=text_normalizer,
        null_scrubber=NullScrubbingService(),
        question_header_resolver=QuestionHeaderResolutionService(text_normalizer),
        verbatim_header_cleaner=VerbatimHeaderCleaningService(text_normalizer),
        vertical_record_filter=VerticalRecordFilterService(),
        duplicate_answer_resolver=DuplicateAnswerResolutionService(),
        metadata_consolidator=MetadataConsolidationService(),
        vertical_record_assembler=VerticalRecordAssemblyService(),
        row_filter=VerbatimRowFilterService(),
    )

    app = FastAPI(title="Verbatim App Ingestion Engine", version="0.1.0")
    app.include_router(
        build_ingest_router(
            ingestion_service=ingestion_service,
            architect_service=architect_service,
            transformation_service=transformation_service,
            preview_size=settings.transformed_preview_size,
        )
    )

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
