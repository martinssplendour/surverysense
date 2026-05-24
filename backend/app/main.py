"""Application factory: wires together all services and mounts the FastAPI app."""
from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.application_setup import (
    build_application_services,
    configure_session_middleware,
    mount_frontend,
    register_application_routers,
    register_frontend_routes,
    register_startup_hooks,
    validate_runtime_settings,
)
from app.core.auth import get_authenticated_user
from app.core.settings import get_settings

PUBLIC_PATH_PREFIXES = ("/static", "/auth", "/health")
PUBLIC_PATHS = {"/", "/login", "/robots.txt", "/sitemap.xml"}
NO_CACHE_PATH_PREFIXES = ("/static",)
NO_CACHE_PATHS = {"/", "/login"}


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
    """Redirects unauthenticated browser GET requests to the login page."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if get_authenticated_user(request) is None and _should_redirect_to_login(request):
            return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        return await call_next(request)


class FrontendCacheControlMiddleware(BaseHTTPMiddleware):
    """Avoid stale frontend asset mixes after Render deploys."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        path = request.url.path
        if path in NO_CACHE_PATHS or any(path.startswith(prefix) for prefix in NO_CACHE_PATH_PREFIXES):
            response.headers["Cache-Control"] = "no-store, max-age=0, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


def create_app() -> FastAPI:
    settings = get_settings()
    validate_runtime_settings(settings)
    services = build_application_services(settings)

    app = FastAPI(title="Verbatim App Ingestion Engine", version="0.1.0")
    # Auth redirect runs outermost so browser page requests bounce to /login before
    # any view logic tries to serve HTML to an unauthenticated user.
    app.add_middleware(AuthRedirectMiddleware)
    app.add_middleware(FrontendCacheControlMiddleware)
    configure_session_middleware(app, settings)
    register_application_routers(app, settings=settings, services=services)
    mount_frontend(app)
    register_startup_hooks(
        app,
        topic_analysis_service=services.topic_analysis_service,
        result_store_service=services.result_store_service,
        result_store_cleanup_interval_seconds=settings.result_store_cleanup_interval_seconds,
    )
    register_frontend_routes(app, settings=settings)
    return app


app = create_app()
