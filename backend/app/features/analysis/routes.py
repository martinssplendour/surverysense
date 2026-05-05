from __future__ import annotations

from fastapi import Query, Request, Response

from app.core.auth import require_authenticated_user, require_session_result_access
from app.features.common.route_context import WorkspaceRouteContext
from app.models.api import (
    AnalysisExportRequest,
    AnalysisGroupDocumentsResponse,
    AnalysisNgramDocumentsResponse,
    AnalysisRunRequest,
    AnalysisRunResponse,
)


def register_analysis_routes(context: WorkspaceRouteContext) -> None:
    _register_run_analysis_route(context)
    _register_group_documents_route(context)
    _register_ngram_documents_route(context)
    _register_export_route(context)


def _register_run_analysis_route(context: WorkspaceRouteContext) -> None:
    def run_analysis(
        request: Request,
        result_id: str,
        analysis_request: AnalysisRunRequest,
    ) -> AnalysisRunResponse:
        require_authenticated_user(request)
        require_session_result_access(request, result_id)
        fast_result = context.result_store_service.get_fast_filtered_result(
            result_id,
            model_key=analysis_request.model_key,
            text_column_name=analysis_request.text_column_name,
            filters=analysis_request.filters or {},
        )
        if fast_result is not None:
            return AnalysisRunResponse.model_validate(fast_result.to_api_payload())

        def _execute() -> AnalysisRunResponse:
            selection = context.result_store_service.get_dataset(
                result_id,
                dataset="analysis",
                filters=analysis_request.filters,
            )
            result = context.topic_analysis_service.run(
                result_id=result_id,
                dataframe=selection.dataframe,
                model_key=analysis_request.model_key,
                text_column_name=analysis_request.text_column_name,
                available_verbatim_columns=selection.verbatim_columns,
            )
            if result.error_code != "gemini_rate_limited":
                context.result_store_service.save_analysis_snapshot(
                    result_id,
                    text_column_name=analysis_request.text_column_name,
                    model_key=analysis_request.model_key,
                    analysis_result=result,
                )
            return AnalysisRunResponse.model_validate(result.to_api_payload())

        return context.execute_api_action("run_analysis", _execute)

    context.router.add_api_route(
        "/run-analysis/{result_id}",
        run_analysis,
        methods=["POST"],
        response_model=AnalysisRunResponse,
    )


def _register_group_documents_route(context: WorkspaceRouteContext) -> None:
    @context.router.get("/analysis-group-documents/{result_id}", response_model=AnalysisGroupDocumentsResponse)
    async def get_analysis_group_documents(
        request: Request,
        result_id: str,
        group_id: str = Query(..., min_length=1),
        offset: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=500),
    ) -> AnalysisGroupDocumentsResponse:
        require_authenticated_user(request)
        require_session_result_access(request, result_id)

        def _execute() -> AnalysisGroupDocumentsResponse:
            page = context.result_store_service.get_analysis_group_page(
                result_id,
                group_id=group_id,
                offset=offset,
                limit=limit,
            )
            return AnalysisGroupDocumentsResponse(
                result_id=page.result_id,
                group_id=page.group_id,
                group_label=page.group_label,
                text_column_name=page.text_column_name,
                total_count=page.total_count,
                offset=page.offset,
                limit=page.limit,
                has_more=page.has_more,
                documents=[document.to_api_payload() for document in page.documents],
            )

        return context.execute_api_action("get_analysis_group_documents", _execute)


def _register_ngram_documents_route(context: WorkspaceRouteContext) -> None:
    @context.router.get("/analysis-ngram-documents/{result_id}", response_model=AnalysisNgramDocumentsResponse)
    async def get_analysis_ngram_documents(
        request: Request,
        result_id: str,
        ngram_size: int = Query(..., ge=1, le=3),
        term: str = Query(..., min_length=1),
        offset: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=500),
    ) -> AnalysisNgramDocumentsResponse:
        require_authenticated_user(request)
        require_session_result_access(request, result_id)

        def _execute() -> AnalysisNgramDocumentsResponse:
            page = context.result_store_service.get_analysis_ngram_page(
                result_id,
                ngram_size=ngram_size,
                term=term,
                offset=offset,
                limit=limit,
            )
            return AnalysisNgramDocumentsResponse(
                result_id=page.result_id,
                term=page.term,
                source_term=page.source_term,
                ngram_size=page.ngram_size,
                text_column_name=page.text_column_name,
                total_count=page.total_count,
                hit_count=page.hit_count,
                offset=page.offset,
                limit=page.limit,
                has_more=page.has_more,
                documents=[document.to_api_payload() for document in page.documents],
            )

        return context.execute_api_action("get_analysis_ngram_documents", _execute)


def _register_export_route(context: WorkspaceRouteContext) -> None:
    def export_analysis_report(
        request: Request,
        result_id: str,
        export_request: AnalysisExportRequest,
    ) -> Response:
        require_authenticated_user(request)
        require_session_result_access(request, result_id)

        def _execute() -> Response:
            context.result_store_service.get_filters(result_id)
            artifact = context.report_export_service.export_report(
                result_id=result_id,
                request=export_request,
            )
            return Response(
                content=artifact.content,
                media_type=artifact.media_type,
                headers={
                    "Content-Disposition": f'attachment; filename="{artifact.filename}"',
                },
            )

        return context.execute_api_action("export_analysis_report", _execute)

    context.router.add_api_route("/analysis-export/{result_id}", export_analysis_report, methods=["POST"])
