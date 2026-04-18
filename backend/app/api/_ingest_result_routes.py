from __future__ import annotations

from fastapi import HTTPException, Query, Request, status

from app.core.auth import require_authenticated_user
from app.models.api import (
    ColumnRoleUpdateRequest,
    ColumnRoleUpdateResponse,
    ResultRowsResponse,
)
from app.services.result_store_service import ResultNotFoundError

from app.api._ingest_route_context import IngestRouteContext


def register_result_routes(context: IngestRouteContext) -> None:
    router = context.router

    @router.post("/result-columns/{result_id}", response_model=ColumnRoleUpdateResponse)
    async def update_result_columns(
        request: Request,
        result_id: str,
        update_request: ColumnRoleUpdateRequest,
    ) -> ColumnRoleUpdateResponse:
        require_authenticated_user(request)
        try:
            stored = context.result_store_service.update_column_role(
                result_id,
                column_name=update_request.column_name,
                role=update_request.role,
            )
        except ResultNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except Exception as exc:
            context.raise_unexpected_api_error("update_result_columns", exc)
        return ColumnRoleUpdateResponse(
            result_id=result_id,
            analysis_metadata_column_names=list(stored.metadata_columns),
            analysis_verbatim_column_names=list(stored.verbatim_columns),
            analysis_row_count=int(len(stored.analysis_df)),
            analysis_column_names=stored.analysis_df.columns.tolist(),
            available_filters=context.serialize_filters(result_id),
        )

    @router.get("/result-rows/{result_id}", response_model=ResultRowsResponse)
    async def get_result_rows(
        request: Request,
        result_id: str,
        dataset: str = Query(..., pattern="^(transformed|analysis)$"),
        offset: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=1000),
        filters: str | None = Query(None),
    ) -> ResultRowsResponse:
        require_authenticated_user(request)
        try:
            page = context.result_store_service.get_page(
                result_id,
                dataset=dataset,
                offset=offset,
                limit=limit,
                filters=context.parse_filters(filters),
            )
        except ResultNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except Exception as exc:
            context.raise_unexpected_api_error("get_result_rows", exc)
        return ResultRowsResponse(
            result_id=page.result_id,
            dataset=page.dataset,
            total_row_count=page.total_row_count,
            unfiltered_row_count=page.unfiltered_row_count,
            offset=page.offset,
            limit=page.limit,
            has_more=page.has_more,
            column_names=page.column_names,
            rows=page.rows,
        )
