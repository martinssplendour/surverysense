from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any

import pandas as pd
from pandas.errors import ParserError

from app.core.exceptions import CsvDecodeError
from app.services.encoding_service import EncodingDetectionResult, EncodingDetectionService


@dataclass(slots=True)
class IngestedCsv:
    dataframe: pd.DataFrame
    sample_df: pd.DataFrame
    architect_df: pd.DataFrame
    encoding_result: EncodingDetectionResult
    column_index_map: dict[int, str]


class CsvIngestionService:
    def __init__(
        self,
        encoding_service: EncodingDetectionService,
        sample_size: int,
        architect_sample_size: int,
    ) -> None:
        self.encoding_service = encoding_service
        self.sample_size = sample_size
        self.architect_sample_size = architect_sample_size

    def ingest(self, payload: bytes) -> IngestedCsv:
        encoding_result = self.encoding_service.detect(payload)
        dataframe = self._read_csv(payload, encoding_result.encoding)
        sample_df = self._head_dataframe(dataframe, self.sample_size)
        architect_df = self._head_dataframe(dataframe, self.architect_sample_size)
        column_index_map = {
            index: str(column_name)
            for index, column_name in enumerate(dataframe.columns.tolist())
        }
        return IngestedCsv(
            dataframe=dataframe,
            sample_df=sample_df,
            architect_df=architect_df,
            encoding_result=encoding_result,
            column_index_map=column_index_map,
        )

    def serialize_sample_rows(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            serialized_row: dict[str, Any] = {}
            for idx, value in enumerate(row.tolist()):
                serialized_row[f"idx_{idx}"] = None if pd.isna(value) else value
            rows.append(serialized_row)
        return rows

    @staticmethod
    def _head_dataframe(df: pd.DataFrame, sample_size: int) -> pd.DataFrame:
        if df.empty:
            return df.copy()
        n_rows = min(sample_size, len(df))
        return df.head(n_rows).reset_index(drop=True)

    @staticmethod
    def _read_csv(payload: bytes, encoding: str) -> pd.DataFrame:
        try:
            return pd.read_csv(
                BytesIO(payload),
                encoding=encoding,
                dtype=object,
                keep_default_na=False,
                low_memory=False,
            )
        except (UnicodeDecodeError, ParserError) as exc:
            raise CsvDecodeError(f"Unable to parse uploaded CSV using {encoding}.") from exc
