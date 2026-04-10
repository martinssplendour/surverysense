from __future__ import annotations

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
from app.services.metadata_filter_service import MetadataFilterService
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

STATIC_DIR = Path(__file__).resolve().parent / "static"
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
    google_oauth_service = GoogleOAuthService(
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
    keyword_service = TopicAnalysisKeywordService()
    narrative_service = TopicAnalysisNarrativeService(keyword_service)
    topic_analysis_service = TopicAnalysisService(
        config=TopicAnalysisConfig(
            embedding_model=settings.topic_embedding_model,
            kmeans_clusters=settings.topic_kmeans_clusters,
            kmeans_random_state=settings.topic_kmeans_random_state,
            hdbscan_min_cluster_size=settings.topic_hdbscan_min_cluster_size,
            hdbscan_min_samples=settings.topic_hdbscan_min_samples,
            hdbscan_metric=settings.topic_hdbscan_metric,
            bertopic_language=settings.topic_bertopic_language,
            top_terms_per_group=settings.topic_top_terms,
            top_ngrams_per_bucket=settings.topic_top_ngrams,
            representative_examples_per_group=settings.topic_representative_examples,
            max_document_chars=settings.topic_max_document_chars,
        ),
        input_validation_service=TopicAnalysisInputValidationService(),
        text_preparation_service=TopicAnalysisTextPreparationService(
            max_document_chars=settings.topic_max_document_chars,
        ),
        keyword_service=keyword_service,
        narrative_service=narrative_service,
        representative_example_service=RepresentativeExampleSelectionService(),
        embedding_service=SentenceEmbeddingService(),
        ngram_service=NgramAnalysisService(keyword_service),
        kmeans_service=KMeansAnalysisService(),
        hdbscan_service=HdbscanAnalysisService(),
        bertopic_service=BertopicAnalysisService(),
    )

    app = FastAPI(title="Verbatim App Ingestion Engine", version="0.1.0")
    app.add_middleware(AuthRedirectMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        same_site="lax",
        https_only=settings.session_https_only,
    )

    app.include_router(build_auth_router(google_oauth_service))
    app.include_router(
        build_ingest_router(
            ingestion_service=ingestion_service,
            architect_service=architect_service,
            transformation_service=transformation_service,
            analysis_ready_service=analysis_ready_service,
            topic_analysis_service=topic_analysis_service,
            result_store_service=result_store_service,
            preview_size=settings.transformed_preview_size,
            architect_sample_size=settings.architect_sample_size,
        )
    )
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False, response_model=None)
    async def index(request: Request):
        if get_authenticated_user(request) is None:
            return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/login", include_in_schema=False, response_model=None)
    async def login(request: Request):
        if get_authenticated_user(request) is not None:
            return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        return FileResponse(STATIC_DIR / "login.html")

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
