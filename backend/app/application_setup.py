"""Shared helpers for the FastAPI application factory."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.core.auth import get_authenticated_user
from app.core.settings import Settings
from app.features.analysis.language_normalization_service import (
    EnglishTranslationConfig,
    EnglishTranslationService,
)
from app.features.analysis.topic_analysis_services import (
    CommunityDetectionAnalysisService,
    NgramAnalysisService,
    RepresentativeExampleSelectionService,
    SentenceEmbeddingService,
    TopicAnalysisConfig,
    TopicAnalysisInputValidationService,
    TopicAnalysisKeywordService,
    TopicAnalysisNarrativeService,
    TopicAnalysisService,
    TopicAnalysisTextPreparationService,
)
from app.features.analysis.topic_label_ai_service import TopicAiLabelingConfig, TopicAiLabelService
from app.features.auth.google_oauth_service import GoogleOAuthService
from app.features.auth.routes import build_auth_router
from app.features.export.report_export_service import AnalysisReportExportService
from app.features.ingestion.architect_service import ManifestArchitectConfig, ManifestArchitectService
from app.features.ingestion.cleaning_services import (
    AnalysisReadyDatasetService,
    DuplicateAnswerResolutionService,
    MetadataColumnSelectionService,
    MetadataConsolidationService,
    MultipartVerbatimConsolidationService,
    NullScrubbingService,
    QuestionHeaderResolutionService,
    TextNormalizationService,
    VerbatimHeaderCleaningService,
    VerbatimQuestionSelectionService,
    VerbatimRowFilterService,
    VerticalRecordAssemblyService,
    VerticalRecordFilterService,
)
from app.features.ingestion.csv_ingestion_service import CsvIngestionService
from app.features.ingestion.encoding_service import EncodingDetectionService
from app.features.ingestion.transformation_service import DataTransformationService
from app.features.results.metadata_filter import MetadataFilterService
from app.features.results.store import ResultStoreService
from app.features.routes import build_workspace_router

logger = logging.getLogger(__name__)

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


@dataclass(slots=True)
class ApplicationServices:
    google_oauth_service: GoogleOAuthService
    ingestion_service: CsvIngestionService
    architect_service: ManifestArchitectService
    transformation_service: DataTransformationService
    analysis_ready_service: AnalysisReadyDatasetService
    topic_analysis_service: TopicAnalysisService
    report_export_service: AnalysisReportExportService
    result_store_service: ResultStoreService
    translation_service: EnglishTranslationService


def validate_runtime_settings(settings: Settings) -> None:
    if not settings.session_secret:
        raise RuntimeError("SESSION_SECRET must be set.")


def build_application_services(settings: Settings) -> ApplicationServices:
    google_oauth_service = GoogleOAuthService(
        client_id=settings.google_oauth_client_id,
        client_secret=settings.google_oauth_client_secret,
        redirect_uris=settings.google_oauth_redirect_uris,
        javascript_origins=settings.google_oauth_javascript_origins,
        client_json_path=settings.google_oauth_client_json_path,
        allowed_domains=settings.google_oauth_allowed_domains,
    )
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
    transformation_service = _build_transformation_service(text_normalizer)
    analysis_ready_service = _build_analysis_ready_service(text_normalizer)
    result_store_service = ResultStoreService(
        MetadataFilterService(),
        analysis_ready_service=analysis_ready_service,
        max_results=settings.result_store_max_results,
        ttl_seconds=settings.result_store_ttl_seconds,
    )
    report_export_service = AnalysisReportExportService(result_store_service=result_store_service)
    translation_service = EnglishTranslationService(
        config=EnglishTranslationConfig(
            enabled=settings.topic_translation_enabled,
            source_language=settings.topic_translation_source_language,
            target_language=settings.topic_translation_target_language,
            batch_size=settings.topic_translation_batch_size,
        )
    )
    topic_analysis_service = _build_topic_analysis_service(
        settings,
        translation_service=translation_service,
    )
    return ApplicationServices(
        google_oauth_service=google_oauth_service,
        ingestion_service=ingestion_service,
        architect_service=architect_service,
        transformation_service=transformation_service,
        analysis_ready_service=analysis_ready_service,
        topic_analysis_service=topic_analysis_service,
        report_export_service=report_export_service,
        result_store_service=result_store_service,
        translation_service=translation_service,
    )


def configure_session_middleware(app: FastAPI, settings: Settings) -> None:
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        max_age=settings.session_idle_timeout_seconds,
        same_site="lax",
        https_only=settings.session_https_only,
    )


def register_application_routers(
    app: FastAPI,
    *,
    settings: Settings,
    services: ApplicationServices,
) -> None:
    app.include_router(
        build_auth_router(
            services.google_oauth_service,
            result_store_service=services.result_store_service,
        )
    )
    app.include_router(
        build_workspace_router(
            ingestion_service=services.ingestion_service,
            architect_service=services.architect_service,
            transformation_service=services.transformation_service,
            analysis_ready_service=services.analysis_ready_service,
            topic_analysis_service=services.topic_analysis_service,
            report_export_service=services.report_export_service,
            result_store_service=services.result_store_service,
            translation_service=services.translation_service,
            architect_sample_size=settings.architect_sample_size,
        )
    )


def mount_frontend(app: FastAPI, *, frontend_dir: Path = FRONTEND_DIR) -> None:
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


def register_startup_hooks(app: FastAPI, *, topic_analysis_service: TopicAnalysisService) -> None:
    @app.on_event("startup")
    async def warm_topic_models() -> None:
        async def _warm_models_after_startup() -> None:
            try:
                await asyncio.to_thread(topic_analysis_service.warm_up)
                logger.info("Topic embedding model warmed and cached for the current process.")
            except Exception as exc:  # pragma: no cover - startup guard
                logger.warning(
                    "Topic model warmup failed during startup (%s). The server will stay up and warm models on the first analysis request instead.",
                    type(exc).__name__,
                )

        app.state.topic_model_warmup_task = asyncio.create_task(_warm_models_after_startup())


def register_frontend_routes(app: FastAPI, *, frontend_dir: Path = FRONTEND_DIR) -> None:
    @app.get("/", include_in_schema=False, response_model=None)
    async def index(request: Request) -> FileResponse | RedirectResponse:
        if get_authenticated_user(request) is None:
            return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        return FileResponse(frontend_dir / "index.html")

    @app.get("/login", include_in_schema=False, response_model=None)
    async def login(request: Request) -> FileResponse | RedirectResponse:
        if get_authenticated_user(request) is not None:
            return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        return FileResponse(frontend_dir / "login.html")

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}


def _build_transformation_service(text_normalizer: TextNormalizationService) -> DataTransformationService:
    return DataTransformationService(
        text_normalizer=text_normalizer,
        null_scrubber=NullScrubbingService(),
        question_header_resolver=QuestionHeaderResolutionService(text_normalizer),
        verbatim_header_cleaner=VerbatimHeaderCleaningService(text_normalizer),
        multipart_verbatim_consolidator=MultipartVerbatimConsolidationService(text_normalizer),
        vertical_record_filter=VerticalRecordFilterService(),
        duplicate_answer_resolver=DuplicateAnswerResolutionService(),
        metadata_consolidator=MetadataConsolidationService(),
        vertical_record_assembler=VerticalRecordAssemblyService(),
        row_filter=VerbatimRowFilterService(),
    )


def _build_analysis_ready_service(text_normalizer: TextNormalizationService) -> AnalysisReadyDatasetService:
    return AnalysisReadyDatasetService(
        metadata_selector=MetadataColumnSelectionService(),
        verbatim_selector=VerbatimQuestionSelectionService(),
        multipart_verbatim_consolidator=MultipartVerbatimConsolidationService(text_normalizer),
        row_filter=VerbatimRowFilterService(),
    )


def _build_topic_analysis_service(
    settings: Settings,
    *,
    translation_service: EnglishTranslationService,
) -> TopicAnalysisService:
    keyword_service = TopicAnalysisKeywordService()
    narrative_service = TopicAnalysisNarrativeService(keyword_service)
    return TopicAnalysisService(
        config=TopicAnalysisConfig(
            embedding_provider=settings.topic_embedding_provider,
            embedding_model=settings.resolved_topic_embedding_model,
            embedding_api_key=settings.resolved_topic_embedding_api_key,
            embedding_dimensions=settings.topic_embedding_dimensions,
            embedding_batch_size=settings.topic_embedding_batch_size,
            embedding_timeout_seconds=settings.topic_embedding_timeout_seconds,
            embedding_fallback_provider=settings.resolved_topic_embedding_fallback_provider,
            embedding_fallback_model=settings.resolved_topic_embedding_fallback_model,
            embedding_fallback_api_key=settings.resolved_topic_embedding_fallback_api_key,
            community_similarity_threshold=settings.topic_community_similarity_threshold,
            community_max_neighbors=settings.topic_community_max_neighbors,
            community_resolution=settings.topic_community_resolution,
            community_mutual_neighbors=settings.topic_community_mutual_neighbors,
            top_terms_per_group=settings.topic_top_terms,
            top_ngrams_per_bucket=settings.topic_top_ngrams,
            representative_examples_per_group=settings.topic_representative_examples,
            max_document_chars=settings.topic_max_document_chars,
        ),
        input_validation_service=TopicAnalysisInputValidationService(),
        text_preparation_service=TopicAnalysisTextPreparationService(
            max_document_chars=settings.topic_max_document_chars,
            translation_service=translation_service,
            input_translation_enabled=settings.topic_input_translation_enabled,
        ),
        keyword_service=keyword_service,
        narrative_service=narrative_service,
        representative_example_service=RepresentativeExampleSelectionService(),
        embedding_service=SentenceEmbeddingService(
            cache_size=settings.topic_embedding_cache_size,
            max_retries=settings.topic_embedding_max_retries,
            retry_base_seconds=settings.topic_embedding_retry_base_seconds,
        ),
        ngram_service=NgramAnalysisService(keyword_service),
        community_detection_service=CommunityDetectionAnalysisService(),
        ai_label_service=TopicAiLabelService(
            config=TopicAiLabelingConfig(
                enabled=settings.topic_ai_labeling_enabled,
                gemini_api_key=settings.gemini_api_key,
                gemini_model=settings.gemini_model,
                gemini_temperature=settings.gemini_temperature,
                timeout_seconds=settings.topic_ai_labeling_timeout_seconds,
                max_groups=settings.topic_ai_labeling_max_groups,
                max_examples_per_group=settings.topic_ai_labeling_max_examples,
                max_terms_per_group=settings.topic_ai_labeling_max_terms,
                max_chars_per_example=settings.topic_ai_labeling_max_chars_per_example,
                max_unigrams=settings.topic_ai_labeling_max_unigrams,
                max_bigrams=settings.topic_ai_labeling_max_bigrams,
                max_trigrams=settings.topic_ai_labeling_max_trigrams,
                min_ngram_document_count=settings.topic_ai_labeling_min_ngram_document_count,
                batch_size=settings.topic_ai_labeling_batch_size,
                max_retries=settings.topic_ai_labeling_max_retries,
                retry_base_seconds=settings.topic_ai_labeling_retry_base_seconds,
            )
        ),
    )
