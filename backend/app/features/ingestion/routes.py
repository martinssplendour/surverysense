from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd
from fastapi import File, Form, HTTPException, Request, UploadFile, status

from app.features.common.route_context import WorkspaceRouteContext
from app.core.auth import register_session_result_id, require_authenticated_user
from app.models.api import DiagnosticConfigResponse, UploadIngestResponse
from app.models.manifest import TransformationManifest
from app.features.ingestion.architect_service import DiagnosticMode
from app.features.ingestion.csv_ingestion_service import IngestedCsv

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _UploadIngestArtifacts:
    result_id: str
    ingested: IngestedCsv
    manifest: TransformationManifest
    transformed_df: pd.DataFrame
    analysis_df: pd.DataFrame
    analysis_metadata_columns: list[str]
    analysis_verbatim_columns: list[str]


def register_upload_routes(context: WorkspaceRouteContext) -> None:
    router = context.router

    @router.get("/diagnostic-config", response_model=DiagnosticConfigResponse)
    async def diagnostic_config(request: Request) -> DiagnosticConfigResponse:
        require_authenticated_user(request)
        default_mode = context.architect_service.default_diagnostic_mode()
        return DiagnosticConfigResponse(
            ai_available=context.architect_service.is_ai_available(),
            default_diagnostic_mode=default_mode.value,
            architect_row_count=context.architect_sample_size,
        )

    @router.post("/upload-ingest", response_model=UploadIngestResponse)
    def upload_ingest(
        request: Request,
        file: UploadFile = File(...),
        diagnostic_mode: DiagnosticMode = Form(DiagnosticMode.AI),
    ) -> UploadIngestResponse:
        require_authenticated_user(request)
        if file.filename and not file.filename.lower().endswith(".csv"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only CSV uploads are supported.",
            )

        payload = file.file.read()
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded CSV is empty.",
            )

        def _execute() -> _UploadIngestArtifacts:
            ingested = context.ingestion_service.ingest(payload)
            logger.info(
                "Upload ingest started for file=%s diagnostic_mode=%s sample_rows=%s source_columns=%s.",
                file.filename or "upload.csv",
                diagnostic_mode.value,
                len(ingested.architect_df),
                len(ingested.column_index_map),
            )
            manifest = context.architect_service.get_transformation_manifest(
                ingested.architect_df,
                ingested.column_index_map,
                diagnostic_mode=diagnostic_mode,
            )
            logger.info(
                "Transformation manifest built for file=%s source=%s layout=%s.",
                file.filename or "upload.csv",
                manifest.diagnostic_source,
                manifest.layout_state,
            )
            transformed_df = context.transformation_service.transform(ingested.dataframe, manifest)
            analysis_df, analysis_metadata_columns, analysis_verbatim_columns = context.analysis_ready_service.build(
                transformed_df
            )
            result_id = context.result_store_service.save(
                transformed_df,
                analysis_df,
                metadata_columns=analysis_metadata_columns,
                verbatim_columns=analysis_verbatim_columns,
            )
            logger.info(
                "Upload ingest completed for file=%s result_id=%s transformed_rows=%s analysis_rows=%s metadata_columns=%s verbatim_columns=%s.",
                file.filename or "upload.csv",
                result_id,
                len(transformed_df),
                len(analysis_df),
                len(analysis_metadata_columns),
                len(analysis_verbatim_columns),
            )
            register_session_result_id(request, result_id)
            return _UploadIngestArtifacts(
                result_id=result_id,
                ingested=ingested,
                manifest=manifest,
                transformed_df=transformed_df,
                analysis_df=analysis_df,
                analysis_metadata_columns=analysis_metadata_columns,
                analysis_verbatim_columns=analysis_verbatim_columns,
            )

        try:
            artifacts = context.execute_api_action("upload_ingest", _execute)
        except HTTPException as exc:
            if exc.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR:
                logger.exception(
                    "Upload ingest failed unexpectedly for file=%s with diagnostic_mode=%s.",
                    file.filename or "upload.csv",
                    diagnostic_mode.value,
                )
            raise

        ingested = artifacts.ingested
        manifest = artifacts.manifest
        transformed_df = artifacts.transformed_df
        analysis_df = artifacts.analysis_df
        analysis_metadata_columns = artifacts.analysis_metadata_columns
        analysis_verbatim_columns = artifacts.analysis_verbatim_columns
        result_id = artifacts.result_id
        return UploadIngestResponse(
            result_id=result_id,
            filename=file.filename or "upload.csv",
            encoding=ingested.encoding_result.encoding,
            raw_row_count=int(len(ingested.dataframe)),
            raw_column_count=int(ingested.dataframe.shape[1]),
            sample_row_count=int(len(ingested.sample_df)),
            architect_row_count=int(len(ingested.architect_df)),
            column_index_map=ingested.column_index_map,
            raw_sample_rows=context.ingestion_service.serialize_sample_rows(ingested.sample_df),
            manifest=manifest,
            transformed_row_count=int(len(transformed_df)),
            transformed_column_names=transformed_df.columns.tolist(),
            transformed_preview_rows=[],
            analysis_metadata_column_names=analysis_metadata_columns,
            analysis_verbatim_column_names=analysis_verbatim_columns,
            analysis_row_count=int(len(analysis_df)),
            analysis_column_names=analysis_df.columns.tolist(),
            analysis_preview_rows=[],
            available_filters=context.serialize_filters(result_id),
        )
