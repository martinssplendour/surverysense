from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from fastapi import Query, Request
from fastapi.responses import Response

from app.core.auth import require_authenticated_user, require_session_result_access
from app.features.common.route_context import WorkspaceRouteContext
from app.features.results.models import DatasetName
from app.models.api import (
    ColumnRoleUpdateRequest,
    ColumnRoleUpdateResponse,
    ResultRowsResponse,
)

ResultExportScope = Literal["clean_data", "verbatim_only"]


def register_result_routes(context: WorkspaceRouteContext) -> None:
    router = context.router

    @router.post("/result-columns/{result_id}", response_model=ColumnRoleUpdateResponse)
    async def update_result_columns(
        request: Request,
        result_id: str,
        update_request: ColumnRoleUpdateRequest,
    ) -> ColumnRoleUpdateResponse:
        require_authenticated_user(request)
        require_session_result_access(request, result_id)

        def _execute() -> ColumnRoleUpdateResponse:
            stored = context.result_store_service.update_column_role(
                result_id,
                column_name=update_request.column_name,
                role=update_request.role,
            )
            return ColumnRoleUpdateResponse(
                result_id=result_id,
                analysis_metadata_column_names=list(stored.metadata_columns),
                analysis_verbatim_column_names=list(stored.verbatim_columns),
                analysis_row_count=int(len(stored.analysis_df)),
                analysis_column_names=stored.analysis_df.columns.tolist(),
                available_filters=context.serialize_filters(result_id),
            )

        return context.execute_api_action("update_result_columns", _execute)

    @router.get("/result-rows/{result_id}", response_model=ResultRowsResponse)
    async def get_result_rows(
        request: Request,
        result_id: str,
        dataset: DatasetName = Query(..., pattern="^(transformed|analysis|community_analysis)$"),
        offset: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=1000),
        filters: str | None = Query(None),
    ) -> ResultRowsResponse:
        require_authenticated_user(request)
        require_session_result_access(request, result_id)

        def _execute() -> ResultRowsResponse:
            page = context.result_store_service.get_page(
                result_id,
                dataset=dataset,
                offset=offset,
                limit=limit,
                filters=context.parse_filters(filters),
            )
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

        return context.execute_api_action("get_result_rows", _execute)

    @router.get("/result-export/{result_id}")
    async def export_result_csv(
        request: Request,
        result_id: str,
        scope: ResultExportScope = Query(..., pattern="^(clean_data|verbatim_only)$"),
        filters: str | None = Query(None),
        source_filename: str | None = Query(None),
    ) -> Response:
        require_authenticated_user(request)
        require_session_result_access(request, result_id)

        def _execute() -> Response:
            parsed_filters = context.parse_filters(filters)
            dataframe = context.result_store_service.get_export_dataframe(
                result_id,
                scope=scope,
                filters=parsed_filters,
            )
            csv_content = dataframe.to_csv(index=False)
            filename = _build_export_filename(
                source_filename=source_filename,
                scope=scope,
                has_filters=bool(parsed_filters),
            )
            return Response(
                content=csv_content.encode("utf-8-sig"),
                media_type="text/csv; charset=utf-8",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                },
            )

        return context.execute_api_action("export_result_csv", _execute)


def _build_export_filename(
    *,
    source_filename: str | None,
    scope: ResultExportScope,
    has_filters: bool,
) -> str:
    base_name = Path(str(source_filename or "verbatim-app.csv")).name
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(base_name).stem).strip("._-") or "verbatim-app"
    scope_suffix = "clean_data" if scope == "clean_data" else "verbatim_columns"
    filtered_suffix = "_filtered" if has_filters else ""
    return f"{stem}_{scope_suffix}{filtered_suffix}.csv"
