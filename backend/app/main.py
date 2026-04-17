from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes_auth import build_auth_router
from app.api.routes_ingest import build_ingest_router
from app.core.auth import get_authenticated_user
from app.core.settings import get_settings
from app.services.architect_service import ManifestArchitectConfig, ManifestArchitectService
from app.services.cleaning_services import (
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
from app.services.csv_ingestion_service import CsvIngestionService
from app.services.encoding_service import EncodingDetectionService
from app.services.google_oauth_service import GoogleOAuthService
from app.services.language_normalization_service import (
    EnglishTranslationConfig,
    EnglishTranslationService,
)
from app.services.metadata_filter_service import MetadataFilterService
from app.services.report_export_service import AnalysisReportExportService
from app.services.topic_label_ai_service import TopicAiLabelingConfig, TopicAiLabelService
from app.services.result_store_service import ResultStoreService
from app.services.topic_analysis_services import (
    BertopicAnalysisService,
    HdbscanAnalysisService,
    KMeansAnalysisService,
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
from app.services.transformation_service import DataTransformationService

logger = logging.getLogger(__name__)

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
PUBLIC_PATH_PREFIXES = ("/static", "/auth", "/health")
PUBLIC_PATHS = {"/login"}


def _should_redirect_to_login(request: Request) -> bool:
    path = request.url.path
    if path in PUBLIC_PATHS:
        return False
    if any(path.startswith(prefix) for prefix in PUBLIC_PATH_PREFIXES):
        return False
    if request.method not in {"GET", "HEAD"}:
        return False

    accept_header = request.headers.get("accept", "")
    return "text/html" in accept_header


class AuthRedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if get_authenticated_user(request) is None and _should_redirect_to_login(request):
            return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        return await call_next(request)


def create_app() -> FastAPI:
    settings = get_settings()
    if not settings.debug and settings.is_default_session_secret:
        raise RuntimeError(
            "SESSION_SECRET must be set to a non-default value outside development/test environments."
        )
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
    transformation_service = DataTransformationService(
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
    analysis_ready_service = AnalysisReadyDatasetService(
        metadata_selector=MetadataColumnSelectionService(),
        verbatim_selector=VerbatimQuestionSelectionService(),
        multipart_verbatim_consolidator=MultipartVerbatimConsolidationService(text_normalizer),
        row_filter=VerbatimRowFilterService(),
    )
    result_store_service = ResultStoreService(
        MetadataFilterService(),
        analysis_ready_service=analysis_ready_service,
    )
    report_export_service = AnalysisReportExportService()
    keyword_service = TopicAnalysisKeywordService()
    narrative_service = TopicAnalysisNarrativeService(keyword_service)
    translation_service = EnglishTranslationService(
        config=EnglishTranslationConfig(
            enabled=settings.topic_translation_enabled,
            source_language=settings.topic_translation_source_language,
            target_language=settings.topic_translation_target_language,
            batch_size=settings.topic_translation_batch_size,
        )
    )
    topic_analysis_service = TopicAnalysisService(
        config=TopicAnalysisConfig(
            embedding_model=settings.topic_embedding_model,
            embedding_local_path=settings.topic_embedding_local_path,
            kmeans_clusters=settings.topic_kmeans_clusters,
            kmeans_random_state=settings.topic_kmeans_random_state,
            hdbscan_min_cluster_size=settings.topic_hdbscan_min_cluster_size,
            hdbscan_min_samples=settings.topic_hdbscan_min_samples,
            hdbscan_metric=settings.topic_hdbscan_metric,
            bertopic_language=settings.topic_bertopic_language,
            bertopic_reduce_outliers=settings.topic_bertopic_reduce_outliers,
            bertopic_outlier_threshold=settings.topic_bertopic_outlier_threshold,
            top_terms_per_group=settings.topic_top_terms,
            top_ngrams_per_bucket=settings.topic_top_ngrams,
            representative_examples_per_group=settings.topic_representative_examples,
            max_document_chars=settings.topic_max_document_chars,
        ),
        input_validation_service=TopicAnalysisInputValidationService(),
        text_preparation_service=TopicAnalysisTextPreparationService(
            max_document_chars=settings.topic_max_document_chars,
            translation_service=translation_service,
        ),
        keyword_service=keyword_service,
        narrative_service=narrative_service,
        representative_example_service=RepresentativeExampleSelectionService(),
        embedding_service=SentenceEmbeddingService(),
        ngram_service=NgramAnalysisService(keyword_service),
        kmeans_service=KMeansAnalysisService(),
        hdbscan_service=HdbscanAnalysisService(),
        bertopic_service=BertopicAnalysisService(),
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
            )
        ),
    )

    app = FastAPI(title="Verbatim App Ingestion Engine", version="0.1.0")
    app.add_middleware(AuthRedirectMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        max_age=settings.session_idle_timeout_seconds,
        same_site="lax",
        https_only=settings.session_https_only,
    )

    app.include_router(
        build_auth_router(
            google_oauth_service,
            result_store_service=result_store_service,
        )
    )
    app.include_router(
        build_ingest_router(
            ingestion_service=ingestion_service,
            architect_service=architect_service,
            transformation_service=transformation_service,
            analysis_ready_service=analysis_ready_service,
            topic_analysis_service=topic_analysis_service,
            report_export_service=report_export_service,
            result_store_service=result_store_service,
            translation_service=translation_service,
            preview_size=settings.transformed_preview_size,
            architect_sample_size=settings.architect_sample_size,
        )
    )
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.on_event("startup")
    async def warm_topic_models() -> None:
        async def _warm_models_after_startup() -> None:
            try:
                await asyncio.to_thread(topic_analysis_service.warm_up)
                logger.info("Topic embedding model warmed and cached for the current process.")
            except Exception as exc:  # pragma: no cover - startup guard
                logger.warning("Topic model warmup failed: %s", exc)

        app.state.topic_model_warmup_task = asyncio.create_task(_warm_models_after_startup())

    @app.get("/", include_in_schema=False, response_model=None)
    async def index(request: Request):
        if get_authenticated_user(request) is None:
            return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        return FileResponse(FRONTEND_DIR / "index.html")

    @app.get("/login", include_in_schema=False, response_model=None)
    async def login(request: Request):
        if get_authenticated_user(request) is not None:
            return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        return FileResponse(FRONTEND_DIR / "login.html")

    @app.get("/results", include_in_schema=False, response_model=None)
    async def results(request: Request):
        if get_authenticated_user(request) is None:
            return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
