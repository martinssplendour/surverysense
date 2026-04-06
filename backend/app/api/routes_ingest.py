from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.core.exceptions import CsvDecodeError, IngestionError, RowLimitExceededError
from app.models.api import UploadIngestResponse
from app.services.architect_service import ManifestArchitectService
from app.services.csv_ingestion_service import CsvIngestionService
from app.services.transformation_service import DataTransformationService


def build_ingest_router(
    ingestion_service: CsvIngestionService,
    architect_service: ManifestArchitectService,
    transformation_service: DataTransformationService,
    preview_size: int,
) -> APIRouter:
    router = APIRouter(tags=["ingestion"])

    @router.post("/upload-ingest", response_model=UploadIngestResponse)
    async def upload_ingest(file: UploadFile = File(...)) -> UploadIngestResponse:
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
            manifest = architect_service.get_transformation_manifest(
                ingested.architect_df,
                ingested.column_index_map,
            )
            transformed_df = transformation_service.transform(ingested.dataframe, manifest)
        except (CsvDecodeError, RowLimitExceededError, IngestionError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

        preview_df = transformed_df.head(preview_size).where(pd.notna(transformed_df.head(preview_size)), None)
        return UploadIngestResponse(
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
            transformed_preview_rows=preview_df.to_dict(orient="records"),
        )

    return router
