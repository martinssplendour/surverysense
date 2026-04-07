from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

import pandas as pd


SMART_APOSTROPHES_PATTERN = re.compile(r"[\u2018\u2019\u0060\u00B4\u2032\u0092]")
NUMERIC_HEADER_PREFIX_PATTERN = re.compile(r"^\s*\d+(?:\.\d+)*\s*[:.)-]\s*")
TRANSFORMED_COLUMN_INDEX_SUFFIX_PATTERN = re.compile(r"__idx_\d+$", re.IGNORECASE)
MULTIPART_VERBATIM_SUFFIX_PATTERNS = (
    re.compile(
        r"^(?P<base>.+?)\s*:\s*(?P<slot_label>word|response|answer|comment|entry|part|item|text)\s*(?P<slot_index>\d+)\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?P<base>.+?)\s*[-/]\s*(?P<slot_label>word|response|answer|comment|entry|part|item|text)\s*(?P<slot_index>\d+)\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?P<base>.+?)\s*\(\s*(?P<slot_label>word|response|answer|comment|entry|part|item|text)\s*(?P<slot_index>\d+)\s*\)\s*$",
        re.IGNORECASE,
    ),
)


class TextNormalizationService:
    """Shared text normalization for muddy survey exports."""

    def normalize_scalar(self, value: Any) -> Any:
        if value is None or pd.isna(value):
            return None
        text = str(value).replace("\ufeff", "")
        text = SMART_APOSTROPHES_PATTERN.sub("'", text)
        text = text.strip().rstrip("'").strip()
        return text

    def clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        return df.apply(lambda col: col.map(self.normalize_scalar))


class NullScrubbingService:
    def scrub_dataframe(self, df: pd.DataFrame, null_equivalents: list[str]) -> pd.DataFrame:
        normalized_nulls = {self._normalize_token(item) for item in null_equivalents}
        normalized_nulls.update({"", "nan", "<na>"})

        def scrub(value: Any) -> Any:
            if value is None or pd.isna(value):
                return None
            token = self._normalize_token(value)
            if token in normalized_nulls:
                return None
            return value

        return df.apply(lambda col: col.map(scrub))

    @staticmethod
    def _normalize_token(value: Any) -> str:
        return str(value).strip().casefold()


class QuestionHeaderResolutionService:
    def __init__(self, text_normalizer: TextNormalizationService) -> None:
        self.text_normalizer = text_normalizer

    def resolve(self, raw_df: pd.DataFrame, question_header_indices: list[int]) -> pd.Series:
        resolved = pd.Series([None] * len(raw_df), index=raw_df.index, dtype=object)
        for idx in question_header_indices:
            candidate = raw_df.iloc[:, idx].map(self.text_normalizer.normalize_scalar)
            candidate = candidate.map(lambda value: None if value in (None, "") else str(value))
            resolved = resolved.where(resolved.notna(), candidate)
        return resolved


@dataclass(slots=True)
class VerbatimHeaderInfo:
    original_header: str
    normalized_header: str
    subject: str | None
    question_family: str | None
    family_key: str


@dataclass(slots=True)
class VerbatimQuestionCandidate:
    column_name: str
    score: float
    is_selected: bool
    reasons: list[str]
    non_blank_count: int
    unique_ratio: float
    avg_length: float
    long_text_ratio: float
    numeric_ratio: float


@dataclass(slots=True)
class MultipartVerbatimPart:
    column_name: str
    base_label: str
    group_key: str
    slot_label: str
    slot_index: int
    column_order: int


class MetadataColumnSelectionService:
    """Identifies business metadata columns to keep alongside verbatim outputs."""

    METADATA_HEADER_TOKENS = {
        "response id",
        "user id",
        "bundle",
        "career",
        "category",
        "group",
        "country",
        "county",
        "state",
        "region",
        "date",
        "month",
        "year",
        "started",
        "completed",
        "time",
    }

    def select_columns(self, df: pd.DataFrame) -> list[str]:
        return [
            column
            for column in df.columns
            if self.is_metadata_column(str(column))
        ]

    def is_metadata_column(self, column_name: str) -> bool:
        if "__idx_" not in column_name:
            return False

        normalized = self._normalize_header(column_name)
        return any(token in normalized for token in self.METADATA_HEADER_TOKENS)

    @staticmethod
    def _normalize_header(column_name: str) -> str:
        base_name = TRANSFORMED_COLUMN_INDEX_SUFFIX_PATTERN.sub("", column_name.strip())
        return re.sub(r"[_\W]+", " ", base_name.casefold()).strip()


class MultipartVerbatimConsolidationService:
    """Merges multi-part verbatim answers such as Word 1 / Word 2 / Word 3 into one column."""

    WORD_SEPARATOR = ", "
    DEFAULT_SEPARATOR = " | "

    def __init__(self, text_normalizer: TextNormalizationService) -> None:
        self.text_normalizer = text_normalizer

    def consolidate(
        self,
        df: pd.DataFrame,
        *,
        metadata_columns: list[str],
    ) -> pd.DataFrame:
        if df.empty:
            return df.copy()

        metadata_columns = [column for column in metadata_columns if column in df.columns]
        metadata_set = set(metadata_columns)
        verbatim_columns = [column for column in df.columns if column not in metadata_set]
        if len(verbatim_columns) < 2:
            return df.copy()

        part_by_column: dict[str, MultipartVerbatimPart] = {}
        grouped_parts: dict[str, list[MultipartVerbatimPart]] = {}
        for order, column in enumerate(verbatim_columns):
            part = self._build_part(str(column), order)
            if part is None:
                continue
            part_by_column[column] = part
            grouped_parts.setdefault(part.group_key, []).append(part)

        if not any(len(parts) >= 2 for parts in grouped_parts.values()):
            return df.copy()

        consolidated_columns: dict[str, pd.Series] = {}
        for column in metadata_columns:
            consolidated_columns[column] = df[column]

        used_labels = set(consolidated_columns)
        handled_groups: set[str] = set()
        for column in verbatim_columns:
            part = part_by_column.get(column)
            if part is None or len(grouped_parts[part.group_key]) < 2:
                consolidated_columns[column] = df[column]
                used_labels.add(column)
                continue

            if part.group_key in handled_groups:
                continue

            handled_groups.add(part.group_key)
            group_parts = sorted(
                grouped_parts[part.group_key],
                key=lambda item: (item.slot_index, item.column_order),
            )
            separator = self._separator_for_group(group_parts)
            output_label = self._make_unique_label(part.base_label, used_labels)
            consolidated_columns[output_label] = self._combine_columns(
                df,
                [item.column_name for item in group_parts],
                separator,
            )

        return pd.DataFrame(consolidated_columns, index=df.index)

    def _build_part(self, column_name: str, column_order: int) -> MultipartVerbatimPart | None:
        normalized = self.text_normalizer.normalize_scalar(column_name)
        normalized = str(normalized) if normalized not in (None, "") else column_name.strip()
        normalized = TRANSFORMED_COLUMN_INDEX_SUFFIX_PATTERN.sub("", normalized).strip()
        normalized = NUMERIC_HEADER_PREFIX_PATTERN.sub("", normalized).strip()
        normalized = re.sub(r"\s+", " ", normalized).strip()

        for pattern in MULTIPART_VERBATIM_SUFFIX_PATTERNS:
            match = pattern.match(normalized)
            if not match:
                continue

            base_label = match.group("base").strip()
            slot_label = match.group("slot_label").casefold()
            slot_index = int(match.group("slot_index"))
            if not base_label:
                return None

            return MultipartVerbatimPart(
                column_name=column_name,
                base_label=base_label,
                group_key=base_label.casefold(),
                slot_label=slot_label,
                slot_index=slot_index,
                column_order=column_order,
            )
        return None

    def _separator_for_group(self, group_parts: list[MultipartVerbatimPart]) -> str:
        if all(part.slot_label == "word" for part in group_parts):
            return self.WORD_SEPARATOR
        return self.DEFAULT_SEPARATOR

    def _combine_columns(
        self,
        df: pd.DataFrame,
        column_names: list[str],
        separator: str,
    ) -> pd.Series:
        return df[column_names].apply(
            lambda row: self._combine_row_values(row.tolist(), separator),
            axis=1,
        )

    @staticmethod
    def _combine_row_values(values: list[Any], separator: str) -> str | None:
        combined_values: list[str] = []
        for value in values:
            if value is None or pd.isna(value):
                continue
            text = str(value).strip()
            if not text:
                continue
            combined_values.append(text)
        if not combined_values:
            return None
        return separator.join(combined_values)

    @staticmethod
    def _make_unique_label(label: str, used_labels: set[str]) -> str:
        if label not in used_labels:
            used_labels.add(label)
            return label

        suffix = 2
        while True:
            candidate = f"{label} ({suffix})"
            if candidate not in used_labels:
                used_labels.add(candidate)
                return candidate
            suffix += 1


class VerbatimHeaderCleaningService:
    def __init__(self, text_normalizer: TextNormalizationService) -> None:
        self.text_normalizer = text_normalizer

    def clean_and_sort(
        self,
        df: pd.DataFrame,
        *,
        metadata_columns: list[str],
    ) -> pd.DataFrame:
        if df.empty:
            return df.copy()

        verbatim_columns = [column for column in df.columns if column not in metadata_columns]
        if not verbatim_columns:
            return df.copy()

        infos = [self._build_header_info(column) for column in verbatim_columns]
        family_counts = Counter(
            info.family_key
            for info in infos
            if info.subject and info.question_family and len(info.question_family) <= 80
        )
        repeated_families = {
            family_key
            for family_key, count in family_counts.items()
            if count >= 2
        }

        rename_map: dict[str, str] = {}
        ordered_infos: list[tuple[tuple[int, str, str, str], VerbatimHeaderInfo]] = []
        used_labels: set[str] = set(metadata_columns)
        for info in infos:
            cleaned_label = info.normalized_header
            sort_group = 1
            sort_primary = info.normalized_header.casefold()
            sort_secondary = ""
            if info.family_key in repeated_families and info.subject and info.question_family:
                cleaned_label = f"{info.question_family} | {info.subject}"
                sort_group = 0
                sort_primary = info.question_family.casefold()
                sort_secondary = info.subject.casefold()

            cleaned_label = self._make_unique_label(cleaned_label, used_labels)
            rename_map[info.original_header] = cleaned_label
            ordered_infos.append(
                ((sort_group, sort_primary, sort_secondary, cleaned_label.casefold()), info)
            )

        ordered_infos.sort(key=lambda item: item[0])
        ordered_verbatim_columns = [rename_map[info.original_header] for _, info in ordered_infos]

        cleaned_df = df.rename(columns=rename_map)
        return cleaned_df[metadata_columns + ordered_verbatim_columns]

    def _build_header_info(self, header: str) -> VerbatimHeaderInfo:
        normalized = self.text_normalizer.normalize_scalar(header)
        normalized = str(normalized) if normalized not in (None, "") else str(header).strip()
        normalized = TRANSFORMED_COLUMN_INDEX_SUFFIX_PATTERN.sub("", normalized).strip()
        normalized = NUMERIC_HEADER_PREFIX_PATTERN.sub("", normalized).strip()

        subject: str | None = None
        question_family: str | None = None
        if ": " in normalized:
            left, right = normalized.split(": ", 1)
            if left.strip() and right.strip():
                subject = left.strip()
                question_family = right.strip()

        family_key = (question_family or normalized).casefold()
        return VerbatimHeaderInfo(
            original_header=header,
            normalized_header=normalized,
            subject=subject,
            question_family=question_family,
            family_key=family_key,
        )

    @staticmethod
    def _make_unique_label(label: str, used_labels: set[str]) -> str:
        if label not in used_labels:
            used_labels.add(label)
            return label

        counter = 2
        while True:
            candidate = f"{label} ({counter})"
            if candidate not in used_labels:
                used_labels.add(candidate)
                return candidate
            counter += 1


class VerbatimQuestionSelectionService:
    HIGH_VARIATION_UNIQUE_RATIO_MIN = 0.35
    HIGH_VARIATION_TOP10_COVERAGE_MAX = 0.55
    HIGH_VARIATION_UNIQUE_COUNT_MIN = 10
    MIN_VARIATION_ROW_COUNT = 20
    LOW_VARIATION_UNIQUE_COUNT_MAX = 12
    LOW_VARIATION_UNIQUE_RATIO_MAX = 0.1
    LOW_VARIATION_TOP5_COVERAGE_MIN = 0.65
    LOW_VARIATION_TOP10_COVERAGE_MIN = 0.8

    def score_columns(
        self,
        df: pd.DataFrame,
        *,
        metadata_columns: list[str],
        min_score: float = 3.5,
    ) -> list[VerbatimQuestionCandidate]:
        candidates: list[VerbatimQuestionCandidate] = []
        for column in df.columns:
            if column in metadata_columns:
                continue
            candidate = self._score_column(df[column], column, min_score=min_score)
            candidates.append(candidate)
        return candidates

    def select_columns(
        self,
        df: pd.DataFrame,
        *,
        metadata_columns: list[str],
        min_score: float = 3.5,
    ) -> list[str]:
        return [
            candidate.column_name
            for candidate in self.score_columns(df, metadata_columns=metadata_columns, min_score=min_score)
            if candidate.is_selected
        ]

    def filter_dataframe(
        self,
        df: pd.DataFrame,
        *,
        metadata_columns: list[str],
        min_score: float = 3.5,
    ) -> pd.DataFrame:
        selected_columns = self.select_columns(df, metadata_columns=metadata_columns, min_score=min_score)
        return df[metadata_columns + selected_columns].copy()

    def _score_column(
        self,
        series: pd.Series,
        column_name: str,
        *,
        min_score: float,
    ) -> VerbatimQuestionCandidate:
        non_blank = series.dropna().astype(str).str.strip()
        non_blank = non_blank[non_blank != ""]
        normalized_header = column_name.strip().casefold()
        reasons: list[str] = []

        if non_blank.empty:
            return VerbatimQuestionCandidate(
                column_name=column_name,
                score=-999.0,
                is_selected=False,
                reasons=["column has no non-blank answers"],
                non_blank_count=0,
                unique_ratio=0.0,
                avg_length=0.0,
                long_text_ratio=0.0,
                numeric_ratio=0.0,
            )

        unique_ratio = non_blank.nunique(dropna=True) / max(len(non_blank), 1)
        avg_length = float(non_blank.str.len().mean())
        long_text_ratio = float((non_blank.str.len() >= 25).mean())
        numeric_ratio = float(pd.to_numeric(non_blank, errors="coerce").notna().mean())
        text_value_ratio = float(non_blank.str.contains(r"[^\W\d_]", regex=True).mean())
        unique_count = int(non_blank.nunique(dropna=True))
        value_distribution = non_blank.value_counts(normalize=True, dropna=True)
        top5_coverage = float(value_distribution.head(5).sum())
        top10_coverage = float(value_distribution.head(10).sum())

        if numeric_ratio >= 1.0:
            return VerbatimQuestionCandidate(
                column_name=column_name,
                score=-999.0,
                is_selected=False,
                reasons=["column is entirely numeric"],
                non_blank_count=int(len(non_blank)),
                unique_ratio=unique_ratio,
                avg_length=avg_length,
                long_text_ratio=long_text_ratio,
                numeric_ratio=numeric_ratio,
            )

        if text_value_ratio <= 0.0:
            return VerbatimQuestionCandidate(
                column_name=column_name,
                score=-999.0,
                is_selected=False,
                reasons=["column does not contain text responses"],
                non_blank_count=int(len(non_blank)),
                unique_ratio=unique_ratio,
                avg_length=avg_length,
                long_text_ratio=long_text_ratio,
                numeric_ratio=numeric_ratio,
            )

        if self._looks_like_high_variation_text(
            non_blank_count=int(len(non_blank)),
            unique_count=unique_count,
            unique_ratio=unique_ratio,
            top10_coverage=top10_coverage,
        ):
            reasons.append("column contains text responses")
            reasons.append("answers are highly varied")
            return VerbatimQuestionCandidate(
                column_name=column_name,
                score=10.0,
                is_selected=True,
                reasons=reasons,
                non_blank_count=int(len(non_blank)),
                unique_ratio=unique_ratio,
                avg_length=avg_length,
                long_text_ratio=long_text_ratio,
                numeric_ratio=numeric_ratio,
            )

        if "|" in column_name:
            return VerbatimQuestionCandidate(
                column_name=column_name,
                score=-999.0,
                is_selected=False,
                reasons=["pipe-separated matrix header"],
                non_blank_count=int(len(non_blank)),
                unique_ratio=unique_ratio,
                avg_length=avg_length,
                long_text_ratio=long_text_ratio,
                numeric_ratio=numeric_ratio,
            )

        if self._looks_like_fixed_response_text(
            non_blank_count=int(len(non_blank)),
            unique_count=unique_count,
            unique_ratio=unique_ratio,
            top5_coverage=top5_coverage,
            top10_coverage=top10_coverage,
        ):
            return VerbatimQuestionCandidate(
                column_name=column_name,
                score=-999.0,
                is_selected=False,
                reasons=["answers look like a fixed-response text set"],
                non_blank_count=int(len(non_blank)),
                unique_ratio=unique_ratio,
                avg_length=avg_length,
                long_text_ratio=long_text_ratio,
                numeric_ratio=numeric_ratio,
            )

        reasons.append("column contains text responses")
        reasons.append("answers are sufficiently varied")

        return VerbatimQuestionCandidate(
            column_name=column_name,
            score=10.0,
            is_selected=True,
            reasons=reasons,
            non_blank_count=int(len(non_blank)),
            unique_ratio=unique_ratio,
            avg_length=avg_length,
            long_text_ratio=long_text_ratio,
            numeric_ratio=numeric_ratio,
        )

    def _looks_like_high_variation_text(
        self,
        *,
        non_blank_count: int,
        unique_count: int,
        unique_ratio: float,
        top10_coverage: float,
    ) -> bool:
        if non_blank_count < self.MIN_VARIATION_ROW_COUNT:
            return False

        if unique_count < self.HIGH_VARIATION_UNIQUE_COUNT_MIN:
            return False

        return (
            unique_ratio >= self.HIGH_VARIATION_UNIQUE_RATIO_MIN
            or top10_coverage <= self.HIGH_VARIATION_TOP10_COVERAGE_MAX
        )

    def _looks_like_fixed_response_text(
        self,
        *,
        non_blank_count: int,
        unique_count: int,
        unique_ratio: float,
        top5_coverage: float,
        top10_coverage: float,
    ) -> bool:
        if non_blank_count < self.MIN_VARIATION_ROW_COUNT:
            return False

        return (
            (unique_count <= self.LOW_VARIATION_UNIQUE_COUNT_MAX and top5_coverage >= self.LOW_VARIATION_TOP5_COVERAGE_MIN)
            or
            (unique_ratio <= self.LOW_VARIATION_UNIQUE_RATIO_MAX and top10_coverage >= self.LOW_VARIATION_TOP10_COVERAGE_MIN)
        )


class AnalysisReadyDatasetService:
    """Builds the final analysis-ready slice from a transformed dataframe."""

    def __init__(
        self,
        metadata_selector: MetadataColumnSelectionService,
        verbatim_selector: VerbatimQuestionSelectionService,
        multipart_verbatim_consolidator: MultipartVerbatimConsolidationService,
    ) -> None:
        self.metadata_selector = metadata_selector
        self.verbatim_selector = verbatim_selector
        self.multipart_verbatim_consolidator = multipart_verbatim_consolidator

    def build(self, df: pd.DataFrame) -> tuple[pd.DataFrame, list[str], list[str]]:
        if df.empty:
            metadata_columns = self.metadata_selector.select_columns(df)
            return df.copy(), metadata_columns, []

        metadata_columns = self.metadata_selector.select_columns(df)
        working_df = self.multipart_verbatim_consolidator.consolidate(
            df,
            metadata_columns=metadata_columns,
        )
        verbatim_columns = self.verbatim_selector.select_columns(
            working_df,
            metadata_columns=metadata_columns,
        )
        selected_columns = metadata_columns + [
            column for column in verbatim_columns
            if column not in set(metadata_columns)
        ]
        return working_df[selected_columns].copy(), metadata_columns, verbatim_columns


class VerticalRecordFilterService:
    def drop_invalid_rows(
        self,
        record_df: pd.DataFrame,
        *,
        key_columns: list[str],
        question_column: str,
        answer_column: str,
    ) -> pd.DataFrame:
        if record_df.empty:
            return record_df.copy()

        key_mask = record_df[key_columns].notna().all(axis=1)
        question_mask = record_df[question_column].notna()
        answer_mask = record_df[answer_column].notna()
        return record_df.loc[key_mask & question_mask & answer_mask].copy()


class DuplicateAnswerResolutionService:
    def resolve(
        self,
        record_df: pd.DataFrame,
        *,
        key_columns: list[str],
        question_column: str,
        answer_column: str,
        order_column: str,
    ) -> pd.DataFrame:
        if record_df.empty:
            return record_df.copy()

        deduped = (
            record_df.sort_values(order_column)
            .drop_duplicates(subset=key_columns + [question_column, answer_column], keep="last")
            .drop_duplicates(subset=key_columns + [question_column], keep="last")
        )
        return deduped.reset_index(drop=True)


class MetadataConsolidationService:
    def consolidate(
        self,
        raw_df: pd.DataFrame,
        *,
        key_indices: list[int],
        metadata_indices: list[int],
        column_name_builder: callable,
    ) -> pd.DataFrame:
        selected_indices = list(dict.fromkeys(key_indices + metadata_indices))
        consolidated = pd.DataFrame(
            {
                column_name_builder(raw_df.columns[idx], idx): raw_df.iloc[:, idx]
                for idx in selected_indices
            }
        )
        key_columns = [
            column_name_builder(raw_df.columns[idx], idx)
            for idx in key_indices
        ]
        value_columns = [column for column in consolidated.columns if column not in key_columns]
        if not value_columns:
            return consolidated.drop_duplicates(subset=key_columns).reset_index(drop=True)

        grouped = (
            consolidated.groupby(key_columns, dropna=False, sort=False)[value_columns]
            .agg(self._first_non_null)
            .reset_index()
        )
        return grouped

    @staticmethod
    def _first_non_null(series: pd.Series) -> Any:
        non_null = series.dropna()
        if non_null.empty:
            return None
        return non_null.iloc[0]


class VerticalRecordAssemblyService:
    def assemble(
        self,
        record_df: pd.DataFrame,
        *,
        key_columns: list[str],
        question_column: str,
        answer_column: str,
    ) -> pd.DataFrame:
        if record_df.empty:
            return pd.DataFrame(columns=key_columns)

        wide_df = (
            record_df.pivot(index=key_columns, columns=question_column, values=answer_column)
            .reset_index()
        )
        wide_df.columns.name = None
        return wide_df


class VerbatimRowFilterService:
    def drop_empty_rows(self, df: pd.DataFrame, verbatim_columns: list[str]) -> pd.DataFrame:
        if not verbatim_columns:
            return df.reset_index(drop=True)
        mask = df[verbatim_columns].notna().any(axis=1)
        return df.loc[mask].reset_index(drop=True)
