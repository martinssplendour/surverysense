from __future__ import annotations

from fastapi import HTTPException, Query, Request, Response, status

from app.core.auth import require_authenticated_user
from app.models.api import (
    AnalysisExportRequest,
    AnalysisGroupDocumentsResponse,
    AnalysisNgramDocumentsResponse,
    AnalysisRunRequest,
    AnalysisRunResponse,
)
from app.services.result_store_service import ResultNotFoundError

from app.api._ingest_route_context import IngestRouteContext


def register_analysis_routes(context: IngestRouteContext) -> None:
    router = context.router

    def run_analysis(
        request: Request,
        result_id: str,
        analysis_request: AnalysisRunRequest,
    ) -> AnalysisRunResponse:
        require_authenticated_user(request)
        fast_result = context.result_store_service.get_fast_filtered_result(
            result_id,
            model_key=analysis_request.model_key,
            text_column_name=analysis_request.text_column_name,
            filters=analysis_request.filters or {},
        )
        if fast_result is not None:
            return AnalysisRunResponse.model_validate(fast_result)

        try:
            selection = context.result_store_service.get_dataset(
                result_id,
                dataset="analysis",
                filters=analysis_request.filters,
            )
        except ResultNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except Exception as exc:
            context.raise_unexpected_api_error("run_analysis", exc)

        result = context.topic_analysis_service.run(
            result_id=result_id,
            dataframe=selection.dataframe,
            model_key=analysis_request.model_key,
            text_column_name=analysis_request.text_column_name,
            available_verbatim_columns=selection.verbatim_columns,
        )
        context.result_store_service.save_analysis_snapshot(
            result_id,
            text_column_name=analysis_request.text_column_name,
            model_key=analysis_request.model_key,
            analysis_result=result,
        )
        return AnalysisRunResponse.model_validate(result)

    router.add_api_route("/run-analysis/{result_id}", run_analysis, methods=["POST"], response_model=AnalysisRunResponse)

    @router.get("/analysis-group-documents/{result_id}", response_model=AnalysisGroupDocumentsResponse)
    async def get_analysis_group_documents(
        request: Request,
        result_id: str,
        group_id: str = Query(..., min_length=1),
        offset: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=500),
    ) -> AnalysisGroupDocumentsResponse:
        require_authenticated_user(request)
        try:
            page = context.result_store_service.get_analysis_group_page(
                result_id,
                group_id=group_id,
                offset=offset,
                limit=limit,
            )
        except ResultNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except Exception as exc:
            context.raise_unexpected_api_error("get_analysis_group_documents", exc)
        return AnalysisGroupDocumentsResponse(
            result_id=page.result_id,
            group_id=page.group_id,
            group_label=page.group_label,
            text_column_name=page.text_column_name,
            total_count=page.total_count,
            offset=page.offset,
            limit=page.limit,
            has_more=page.has_more,
            documents=page.documents,
        )

    @router.get("/analysis-ngram-documents/{result_id}", response_model=AnalysisNgramDocumentsResponse)
    async def get_analysis_ngram_documents(
        request: Request,
        result_id: str,
        ngram_size: int = Query(..., ge=1, le=3),
        term: str = Query(..., min_length=1),
        offset: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=500),
    ) -> AnalysisNgramDocumentsResponse:
        require_authenticated_user(request)
        try:
            page = context.result_store_service.get_analysis_ngram_page(
                result_id,
                ngram_size=ngram_size,
                term=term,
                offset=offset,
                limit=limit,
            )
        except ResultNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except Exception as exc:
            context.raise_unexpected_api_error("get_analysis_ngram_documents", exc)
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
            documents=page.documents,
        )

    def export_analysis_report(
        request: Request,
        result_id: str,
        export_request: AnalysisExportRequest,
    ) -> Response:
        require_authenticated_user(request)
        try:
            context.result_store_service.get_filters(result_id)
            artifact = context.report_export_service.export_report(
                result_id=result_id,
                request=export_request,
            )
        except ResultNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except Exception as exc:
            context.raise_unexpected_api_error("export_analysis_report", exc)
        return Response(
            content=artifact.content,
            media_type=artifact.media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{artifact.filename}"',
            },
        )

    router.add_api_route("/analysis-export/{result_id}", export_analysis_report, methods=["POST"])
