from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.core.auth import (
    AuthenticatedUser,
    clear_authenticated_user,
    get_authenticated_user,
    pop_session_result_ids,
    set_authenticated_user,
)
from app.models.auth import (
    AuthConfigResponse,
    AuthSessionResponse,
    GoogleCredentialRequest,
)
from app.services.google_oauth_service import (
    GoogleOAuthConfigurationError,
    GoogleOAuthService,
)
from app.services.result_store_service import ResultStoreService


def build_auth_router(
    google_oauth_service: GoogleOAuthService,
    *,
    result_store_service: ResultStoreService | None = None,
) -> APIRouter:
    router = APIRouter(tags=["auth"])

    @router.get("/auth/config", response_model=AuthConfigResponse)
    async def get_auth_config() -> AuthConfigResponse:
        return AuthConfigResponse(
            is_configured=google_oauth_service.is_configured,
            client_id=google_oauth_service.client_id,
            allowed_domains=list(google_oauth_service.allowed_domains),
        )

    @router.get("/auth/session", response_model=AuthSessionResponse)
    async def get_auth_session(request: Request) -> AuthSessionResponse:
        user = get_authenticated_user(request)
        return AuthSessionResponse(
            is_authenticated=user is not None,
            email=user.email if user else None,
            name=user.name if user else None,
            picture=user.picture if user else None,
        )

    @router.post("/auth/google", response_model=AuthSessionResponse)
    async def authenticate_google(
        payload: GoogleCredentialRequest,
        request: Request,
    ) -> AuthSessionResponse:
        try:
            verified_user = google_oauth_service.verify_credential(payload.credential)
        except PermissionError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except GoogleOAuthConfigurationError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

        session_user = AuthenticatedUser(
            email=verified_user.email,
            name=verified_user.name,
            picture=verified_user.picture,
        )
        set_authenticated_user(request, session_user)
        return AuthSessionResponse(
            is_authenticated=True,
            email=session_user.email,
            name=session_user.name,
            picture=session_user.picture,
        )

    @router.get("/auth/logout", include_in_schema=False, response_model=None)
    async def logout(request: Request):
        session_result_ids = pop_session_result_ids(request)
        clear_authenticated_user(request)
        request.session.clear()
        if result_store_service is not None:
            for result_id in session_result_ids:
                result_store_service.delete(result_id)
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    return router
