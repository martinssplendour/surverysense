"""Reads a raw CSV payload into DataFrames and produces preview/architect samples."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from io import BytesIO
from typing import Any

import pandas as pd
from pandas.errors import ParserError

from app.core.exceptions import CsvDecodeError
from app.features.ingestion.encoding_service import EncodingDetectionResult, EncodingDetectionService


@dataclass(slots=True)
class IngestedCsv:
    """Output of a successful CSV ingest: full dataframe, UI sample, architect sample, detected encoding, and column index map."""

    dataframe: pd.DataFrame
    sample_df: pd.DataFrame
    architect_df: pd.DataFrame
    encoding_result: EncodingDetectionResult
    column_index_map: dict[int, str]


class CsvIngestionService:
    """Orchestrates encoding detection, CSV parsing, and sample slicing for an uploaded file."""
    DELIMITER_CANDIDATES = (",", "\t", ";", "|")
    DETECTION_SAMPLE_BYTES = 65536

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
        """Serialise sample rows as index-keyed dicts (idx_0, idx_1, ...) to avoid header-name collisions in JSON."""
        col_keys = [f"idx_{i}" for i in range(len(df.columns))]
        arr = df.to_numpy(dtype=object, na_value=None)
        return [dict(zip(col_keys, row)) for row in arr.tolist()]

    @staticmethod
    def _head_dataframe(df: pd.DataFrame, sample_size: int) -> pd.DataFrame:
        if df.empty:
            return df.copy()
        n_rows = min(sample_size, len(df))
        return df.head(n_rows).reset_index(drop=True)

    @staticmethod
    def _read_csv(payload: bytes, encoding: str) -> pd.DataFrame:
        delimiters = CsvIngestionService._candidate_delimiters(payload, encoding)
        last_error: Exception | None = None
        for delimiter in delimiters:
            try:
                return pd.read_csv(
                    BytesIO(payload),
                    encoding=encoding,
                    sep=delimiter,
                    dtype=object,
                    keep_default_na=False,
                    low_memory=False,
                )
            except (UnicodeDecodeError, ParserError) as exc:
                last_error = exc

        raise CsvDecodeError("please reexport to csv") from last_error

    @classmethod
    def _candidate_delimiters(cls, payload: bytes, encoding: str) -> list[str]:
        detected = cls._detect_delimiter(payload, encoding)
        if detected:
            return [detected]
        return list(cls.DELIMITER_CANDIDATES)

    @classmethod
    def _detect_delimiter(cls, payload: bytes, encoding: str) -> str:
        sample = cls._decode_detection_sample(payload, encoding)
        if not sample.strip():
            return ""

        try:
            dialect = csv.Sniffer().sniff(sample, delimiters="".join(cls.DELIMITER_CANDIDATES))
        except csv.Error:
            return cls._guess_delimiter_from_sample(sample)

        delimiter = str(dialect.delimiter or "")
        return delimiter if delimiter in cls.DELIMITER_CANDIDATES else ""

    @classmethod
    def _decode_detection_sample(cls, payload: bytes, encoding: str) -> str:
        return payload[: cls.DETECTION_SAMPLE_BYTES].decode(encoding, errors="ignore")

    @classmethod
    def _guess_delimiter_from_sample(cls, sample: str) -> str:
        lines = [line for line in sample.splitlines()[:25] if line.strip()]
        if not lines:
            return ""

        best_delimiter = ""
        best_score: tuple[int, int, int] = (0, 0, 0)
        for delimiter in cls.DELIMITER_CANDIDATES:
            counts = [line.count(delimiter) for line in lines]
            positive_counts = [count for count in counts if count > 0]
            if not positive_counts:
                continue
            common_count = max(set(positive_counts), key=positive_counts.count)
            consistent_rows = positive_counts.count(common_count)
            score = (consistent_rows, common_count, len(positive_counts))
            if score > best_score:
                best_score = score
                best_delimiter = delimiter
        return best_delimiter
