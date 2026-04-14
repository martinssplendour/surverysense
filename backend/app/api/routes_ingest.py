from __future__ import annotations

import json
import logging

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile, status

from app.core.auth import require_authenticated_user
from app.core.exceptions import CsvDecodeError, IngestionError, RowLimitExceededError
from app.models.api import (
    AnalysisGroupDocumentsResponse,
    AnalysisRunRequest,
    AnalysisRunResponse,
    ColumnRoleUpdateRequest,
    ColumnRoleUpdateResponse,
    DiagnosticConfigResponse,
    MetadataFilterDefinitionModel,
    MetadataFilterOptionModel,
    ResultRowsResponse,
    UploadIngestResponse,
)
from app.services.architect_service import DiagnosticMode, ManifestArchitectService
from app.services.cleaning_services import AnalysisReadyDatasetService
from app.services.csv_ingestion_service import CsvIngestionService
from app.services.result_store_service import ResultNotFoundError, ResultStoreService
from app.services.topic_analysis_services import TopicAnalysisService
from app.services.transformation_service import DataTransformationService

logger = logging.getLogger(__name__)


def build_ingest_router(
    ingestion_service: CsvIngestionService,
    architect_service: ManifestArchitectService,
    transformation_service: DataTransformationService,
    analysis_ready_service: AnalysisReadyDatasetService,
    topic_analysis_service: TopicAnalysisService,
    result_store_service: ResultStoreService,
    preview_size: int,
    architect_sample_size: int,
) -> APIRouter:
    router = APIRouter(tags=["ingestion"])

    def serialize_filters(result_id: str) -> list[MetadataFilterDefinitionModel]:
        definitions = result_store_service.get_filters(result_id)
        return [
            MetadataFilterDefinitionModel(
                column_name=definition.column_name,
                display_name=definition.display_name,
                options=[
                    MetadataFilterOptionModel(value=option.value, count=option.count)
                    for option in definition.options
                ],
            )
            for definition in definitions
        ]

    def parse_filters(raw_filters: str | None) -> dict[str, list[str]]:
        if raw_filters is None or not raw_filters.strip():
            return {}

        try:
            parsed = json.loads(raw_filters)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="filters must be valid JSON.",
            ) from exc

        if not isinstance(parsed, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="filters must be a JSON object keyed by column name.",
            )

        normalized: dict[str, list[str]] = {}
        for key, value in parsed.items():
            if not isinstance(key, str):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="filter column names must be strings.",
                )
            if isinstance(value, str):
                values = [value]
            elif isinstance(value, list):
                values = [item for item in value if isinstance(item, str)]
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"filter values for '{key}' must be a string or string array.",
                )
            normalized[key] = values
        return normalized

    @router.get("/diagnostic-config", response_model=DiagnosticConfigResponse)
    async def diagnostic_config(request: Request) -> DiagnosticConfigResponse:
        require_authenticated_user(request)
        default_mode = architect_service.default_diagnostic_mode()
        return DiagnosticConfigResponse(
            ai_available=architect_service.is_ai_available(),
            default_diagnostic_mode=default_mode.value,
            architect_row_count=architect_sample_size,
        )

    @router.post("/upload-ingest", response_model=UploadIngestResponse)
    async def upload_ingest(
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

        payload = await file.read()
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded CSV is empty.",
            )

        try:
            ingested = ingestion_service.ingest(payload)
            logger.info(
                "Upload ingest started for file=%s with diagnostic_mode=%s.",
                file.filename or "upload.csv",
                diagnostic_mode.value,
            )
            manifest = architect_service.get_transformation_manifest(
                ingested.architect_df,
                ingested.column_index_map,
                diagnostic_mode=diagnostic_mode,
            )
            logger.info(
                "Manifest built for file=%s using source=%s and layout=%s.",
                file.filename or "upload.csv",
                manifest.diagnostic_source,
                manifest.layout_state,
            )
            transformed_df = transformation_service.transform(ingested.dataframe, manifest)
            analysis_df, analysis_metadata_columns, analysis_verbatim_columns = analysis_ready_service.build(
                transformed_df
            )
            result_id = result_store_service.save(
                transformed_df,
                analysis_df,
                metadata_columns=analysis_metadata_columns,
                verbatim_columns=analysis_verbatim_columns,
            )
        except (CsvDecodeError, RowLimitExceededError, IngestionError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

        return UploadIngestResponse(
            result_id=result_id,
            filename=file.filename or "upload.csv",
            encoding=ingested.encoding_result.encoding,
            raw_row_count=int(len(ingested.dataframe)),
            raw_column_count=int(ingested.dataframe.shape[1]),
            sample_row_count=int(len(ingested.sample_df)),
            architect_row_count=int(len(ingested.architect_df)),
            column_index_map=ingested.column_index_map,
            raw_sample_rows=ingestion_service.serialize_sample_rows(ingested.sample_df),
            manifest=manifest,
            transformed_row_count=int(len(transformed_df)),
            transformed_column_names=transformed_df.columns.tolist(),
            transformed_preview_rows=[],
            analysis_metadata_column_names=analysis_metadata_columns,
            analysis_verbatim_column_names=analysis_verbatim_columns,
            analysis_row_count=int(len(analysis_df)),
            analysis_column_names=analysis_df.columns.tolist(),
            analysis_preview_rows=[],
            available_filters=serialize_filters(result_id),
        )

    @router.post("/run-analysis/{result_id}", response_model=AnalysisRunResponse)
    async def run_analysis(
        request: Request,
        result_id: str,
        analysis_request: AnalysisRunRequest,
    ) -> AnalysisRunResponse:
        require_authenticated_user(request)
        try:
            selection = result_store_service.get_dataset(
                result_id,
                dataset="analysis",
                filters=analysis_request.filters,
            )
        except ResultNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        result = topic_analysis_service.run(
            result_id=result_id,
            dataframe=selection.dataframe,
            model_key=analysis_request.model_key,
            text_column_name=analysis_request.text_column_name,
            available_verbatim_columns=selection.verbatim_columns,
        )
        result_store_service.save_analysis_snapshot(
            result_id,
            text_column_name=analysis_request.text_column_name,
            analysis_result=result,
        )
        return AnalysisRunResponse.model_validate(result)

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
            page = result_store_service.get_analysis_group_page(
                result_id,
                group_id=group_id,
                offset=offset,
                limit=limit,
            )
        except ResultNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

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

    @router.post("/result-columns/{result_id}", response_model=ColumnRoleUpdateResponse)
    async def update_result_columns(
        request: Request,
        result_id: str,
        update_request: ColumnRoleUpdateRequest,
    ) -> ColumnRoleUpdateResponse:
        require_authenticated_user(request)
        try:
            stored = result_store_service.update_column_role(
                result_id,
                column_name=update_request.column_name,
                role=update_request.role,
            )
        except ResultNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        return ColumnRoleUpdateResponse(
            result_id=result_id,
            analysis_metadata_column_names=list(stored.metadata_columns),
            analysis_verbatim_column_names=list(stored.verbatim_columns),
            analysis_row_count=int(len(stored.analysis_df)),
            analysis_column_names=stored.analysis_df.columns.tolist(),
            available_filters=serialize_filters(result_id),
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
            page = result_store_service.get_page(
                result_id,
                dataset=dataset,
                offset=offset,
                limit=limit,
                filters=parse_filters(filters),
            )
        except ResultNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

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

    return router
