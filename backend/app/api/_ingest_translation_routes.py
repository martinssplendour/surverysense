from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.core.auth import require_authenticated_user
from app.models.api import TranslateTextRequest, TranslateTextResponse

from app.api._ingest_route_context import IngestRouteContext


def register_translation_routes(context: IngestRouteContext) -> None:
    router = context.router

    @router.post("/translate-to-english", response_model=TranslateTextResponse)
    def translate_to_english(
        request: Request,
        translate_request: TranslateTextRequest,
    ) -> TranslateTextResponse:
        require_authenticated_user(request)
        source_text = translate_request.text.strip()
        if not source_text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Text is required for translation.",
            )

        try:
            result = context.translation_service.translate([source_text])
        except Exception as exc:
            context.raise_unexpected_api_error("translate_to_english", exc)

        translated_text = result.texts[0] if result.texts else source_text
        translated = bool(result.translated_flags[0]) if result.translated_flags else False
        warning = result.warnings[0] if result.warnings else None
        return TranslateTextResponse(
            original_text=source_text,
            translated_text=translated_text,
            translated=translated,
            warning=warning,
        )
