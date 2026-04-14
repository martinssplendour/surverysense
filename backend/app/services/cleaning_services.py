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

    def clean_series(self, col: pd.Series) -> pd.Series:
        """Vectorised equivalent of col.map(normalize_scalar)."""
        null_mask = col.isna()
        text = col.where(~null_mask, "").astype(str)
        text = text.str.replace("\ufeff", "", regex=False)
        text = text.str.replace(SMART_APOSTROPHES_PATTERN.pattern, "'", regex=True)
        text = text.str.strip().str.rstrip("'").str.strip()
        return text.where(~null_mask, other=None)

    def clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame(
            {col_name: self.clean_series(df[col_name]) for col_name in df.columns},
            index=df.index,
        )


class NullScrubbingService:
    def scrub_dataframe(self, df: pd.DataFrame, null_equivalents: list[str]) -> pd.DataFrame:
        normalized_nulls = {self._normalize_token(item) for item in null_equivalents}
        normalized_nulls.update({"", "nan", "<na>"})

        cleaned = {}
        for col_name in df.columns:
            col = df[col_name]
            null_mask = col.isna()
            # Normalise each value to its stripped/casefolded token, then check membership.
            token = col.where(~null_mask, "").astype(str).str.strip().str.casefold()
            is_null = null_mask | token.isin(normalized_nulls)
            # Preserve the original (non-stringified) value for survivors.
            cleaned[col_name] = col.where(~is_null, other=None)
        return pd.DataFrame(cleaned, index=df.index)

    @staticmethod
    def _normalize_token(value: Any) -> str:
        return str(value).strip().casefold()


class QuestionHeaderResolutionService:
    def __init__(self, text_normalizer: TextNormalizationService) -> None:
        self.text_normalizer = text_normalizer

    def resolve(self, raw_df: pd.DataFrame, question_header_indices: list[int]) -> pd.Series:
        resolved = pd.Series([None] * len(raw_df), index=raw_df.index, dtype=object)
        _null_like = frozenset({"nan", "<na>", "none"})
        for idx in question_header_indices:
            # Vectorised: clean the column then filter out empty / null-like strings.
            candidate = self.text_normalizer.clean_series(raw_df.iloc[:, idx])
            bad = candidate.isna() | (candidate == "") | candidate.str.casefold().isin(_null_like)
            candidate = candidate.where(~bad, other=None)
            resolved = resolved.where(resolved.notna(), candidate)
        return resolved

    @staticmethod
    def _normalize_resolved_value(value: Any) -> str | None:
        if value is None or pd.isna(value):
            return None
        text = str(value).strip()
        if not text:
            return None
        if text.casefold() in {"nan", "<na>", "none"}:
            return None
        return text


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

    STRONG_METADATA_PHRASES = {
        "account id",
        "age band",
        "age group",
        "case id",
        "contact id",
        "country code",
        "country group",
        "country tier",
        "career category",
        "career group",
        "completed at",
        "csat score",
        "customer id",
        "customer type",
        "date created",
        "end date",
        "interview length",
        "job role",
        "job title",
        "last updated",
        "organization type",
        "panelist id",
        "participant id",
        "nps score",
        "product family",
        "project id",
        "project name",
        "purchase group",
        "purchase type",
        "questionnaire version",
        "record id",
        "renewal group",
        "renewal type",
        "respondent id",
        "response date",
        "response id",
        "response month",
        "response time",
        "ces score",
        "score band",
        "session id",
        "simplified career",
        "start date",
        "started at",
        "state code",
        "study id",
        "study name",
        "submission date",
        "submission id",
        "submission month",
        "submit date",
        "sub type",
        "survey id",
        "survey month",
        "survey name",
        "survey title",
        "survey wave",
        "subscription tenure",
        "time spent",
        "user date created",
        "user id",
        "us states",
        "wave number",
        "rfm status",
        "zip code",
    }
    STRONG_METADATA_WORDS = {
        "age",
        "bundle",
        "career",
        "city",
        "cohort",
        "completed",
        "country",
        "county",
        "department",
        "duration",
        "gender",
        "group",
        "language",
        "locale",
        "market",
        "month",
        "province",
        "region",
        "role",
        "segment",
        "started",
        "state",
        "tier",
        "tenure",
        "wave",
    }
    APPROVED_METADATA_TOKEN_SETS = {
        frozenset({"account", "id"}),
        frozenset({"age", "band"}),
        frozenset({"age", "group"}),
        frozenset({"case", "id"}),
        frozenset({"contact", "id"}),
        frozenset({"country", "code"}),
        frozenset({"country", "group"}),
        frozenset({"country", "tier"}),
        frozenset({"career", "category"}),
        frozenset({"career", "group"}),
        frozenset({"csat", "score"}),
        frozenset({"customer", "id"}),
        frozenset({"customer", "type"}),
        frozenset({"date", "created"}),
        frozenset({"end", "date"}),
        frozenset({"interview", "length"}),
        frozenset({"job", "role"}),
        frozenset({"job", "title"}),
        frozenset({"last", "updated"}),
        frozenset({"organization", "type"}),
        frozenset({"panelist", "id"}),
        frozenset({"participant", "id"}),
        frozenset({"nps", "score"}),
        frozenset({"product", "family"}),
        frozenset({"project", "id"}),
        frozenset({"project", "name"}),
        frozenset({"purchase", "group"}),
        frozenset({"purchase", "type"}),
        frozenset({"questionnaire", "version"}),
        frozenset({"record", "id"}),
        frozenset({"renewal", "group"}),
        frozenset({"renewal", "type"}),
        frozenset({"respondent", "id"}),
        frozenset({"response", "date"}),
        frozenset({"response", "id"}),
        frozenset({"response", "month"}),
        frozenset({"response", "time"}),
        frozenset({"ces", "score"}),
        frozenset({"score", "band"}),
        frozenset({"session", "id"}),
        frozenset({"simplified", "career"}),
        frozenset({"start", "date"}),
        frozenset({"state", "code"}),
        frozenset({"study", "id"}),
        frozenset({"study", "name"}),
        frozenset({"submission", "date"}),
        frozenset({"submission", "id"}),
        frozenset({"submission", "month"}),
        frozenset({"submit", "date"}),
        frozenset({"sub", "type"}),
        frozenset({"survey", "id"}),
        frozenset({"survey", "month"}),
        frozenset({"survey", "name"}),
        frozenset({"survey", "title"}),
        frozenset({"survey", "wave"}),
        frozenset({"subscription", "tenure"}),
        frozenset({"time", "spent"}),
        frozenset({"user", "date", "created"}),
        frozenset({"user", "id"}),
        frozenset({"us", "states"}),
        frozenset({"wave", "number"}),
        frozenset({"rfm", "status"}),
        frozenset({"zip", "code"}),
    }
    QUESTION_LIKE_TOKENS = {
        "how",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "would",
        "could",
        "should",
        "please",
        "thanks",
        "tell",
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
        if normalized in self.STRONG_METADATA_PHRASES:
            return True

        if normalized in self.STRONG_METADATA_WORDS:
            return True

        tokens = normalized.split()
        token_set = set(tokens)
        if self._looks_like_identifier_header(tokens):
            return True
        if len(tokens) <= 4 and any(required_tokens <= token_set for required_tokens in self.APPROVED_METADATA_TOKEN_SETS):
            return True

        return False

    @staticmethod
    def _normalize_header(column_name: str) -> str:
        base_name = TRANSFORMED_COLUMN_INDEX_SUFFIX_PATTERN.sub("", column_name.strip())
        return re.sub(r"[_\W]+", " ", base_name.casefold()).strip()

    @classmethod
    def _looks_like_identifier_header(cls, tokens: list[str]) -> bool:
        if not tokens or len(tokens) > 4:
            return False
        if any(token in cls.QUESTION_LIKE_TOKENS for token in tokens):
            return False
        if tokens[-1] == "id":
            return True
        return any(token in {"uid", "sid", "cid"} for token in tokens)


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
        # Build stripped, empty-string-for-null series per column, then merge iteratively.
        # This is fully vectorised and avoids apply(axis=1) and stack() entirely.
        texts = [
            df[col].where(df[col].notna(), "").astype(str).str.strip()
            for col in column_names
        ]
        result = texts[0].copy()
        for text in texts[1:]:
            both = (result != "") & (text != "")
            only_right = (result == "") & (text != "")
            result = result.where(~both, result + separator + text)
            result = result.where(~only_right, text)
        return result.where(result != "", other=None)

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
    SHORT_TEXT_AVG_LENGTH_MAX = 20.0
    SHORT_TEXT_LONG_RATIO_MAX = 0.2
    SHORT_TEXT_TOP10_COVERAGE_MAX = 0.75
    SHORT_TEXT_UNIQUE_COUNT_MIN = 8
    SMALL_SAMPLE_FIXED_RESPONSE_MIN_ROWS = 8
    SMALL_SAMPLE_FIXED_RESPONSE_UNIQUE_COUNT_MAX = 5
    SMALL_SAMPLE_FIXED_RESPONSE_UNIQUE_RATIO_MAX = 0.35
    SMALL_SAMPLE_FIXED_RESPONSE_TOP5_COVERAGE_MIN = 0.85
    LOW_VARIATION_UNIQUE_COUNT_MAX = 12
    LOW_VARIATION_UNIQUE_RATIO_MAX = 0.1
    LOW_VARIATION_TOP5_COVERAGE_MIN = 0.65
    LOW_VARIATION_TOP10_COVERAGE_MIN = 0.8
    IDENTIFIER_NUMERIC_RATIO_MIN = 0.95
    IDENTIFIER_UNIQUE_RATIO_MIN = 0.85
    OPEN_ENDED_HEADER_PHRASES = (
        "what more",
        "how can",
        "tell us more",
        "please tell",
        "in your own words",
        "comes to mind",
        "other than",
        "three words",
        "why do",
        "why did",
    )
    OPEN_ENDED_HEADER_TOKENS = {
        "comment",
        "comments",
        "describe",
        "feedback",
        "opinion",
        "share",
        "why",
    }
    CLOSED_QUESTION_HEADER_PHRASES = (
        "how important",
        "how well do we",
        "how likely",
        "how many",
        "which of the following",
        "are you happy",
        "awareness and usage",
        "i have heard of this",
        "i have used this",
    )

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
        normalized_header = self._normalize_header(column_name)
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

        unique_count = int(non_blank.nunique(dropna=True))
        unique_ratio = unique_count / max(len(non_blank), 1)
        avg_length = float(non_blank.str.len().mean())
        long_text_ratio = float((non_blank.str.len() >= 25).mean())
        numeric_ratio = float(pd.to_numeric(non_blank, errors="coerce").notna().mean())
        text_value_ratio = float(non_blank.str.contains(r"[^\W\d_]", regex=True).mean())
        value_distribution = non_blank.value_counts(normalize=True, dropna=True)
        top5_coverage = float(value_distribution.head(5).sum())
        top10_coverage = float(value_distribution.head(10).sum())
        header_has_open_cue = self._has_open_ended_header_cue(normalized_header)
        header_looks_closed = self._looks_like_closed_question_header(normalized_header)

        if self._looks_like_identifier_header(normalized_header.split()):
            return VerbatimQuestionCandidate(
                column_name=column_name,
                score=-999.0,
                is_selected=False,
                reasons=["identifier-like header"],
                non_blank_count=int(len(non_blank)),
                unique_ratio=unique_ratio,
                avg_length=avg_length,
                long_text_ratio=long_text_ratio,
                numeric_ratio=numeric_ratio,
            )

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

        if (
            len(non_blank) >= self.MIN_VARIATION_ROW_COUNT
            and numeric_ratio >= self.IDENTIFIER_NUMERIC_RATIO_MIN
            and unique_ratio >= self.IDENTIFIER_UNIQUE_RATIO_MIN
        ):
            return VerbatimQuestionCandidate(
                column_name=column_name,
                score=-999.0,
                is_selected=False,
                reasons=["column looks like identifier values"],
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
            if self._looks_like_short_text_label_set(
                avg_length=avg_length,
                long_text_ratio=long_text_ratio,
            ) and not header_has_open_cue:
                return VerbatimQuestionCandidate(
                    column_name=column_name,
                    score=-999.0,
                    is_selected=False,
                    reasons=["short structured answers without open-ended question cues"],
                    non_blank_count=int(len(non_blank)),
                    unique_ratio=unique_ratio,
                    avg_length=avg_length,
                    long_text_ratio=long_text_ratio,
                    numeric_ratio=numeric_ratio,
                )
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

        if header_looks_closed and self._looks_like_short_text_label_set(
            avg_length=avg_length,
            long_text_ratio=long_text_ratio,
        ):
            return VerbatimQuestionCandidate(
                column_name=column_name,
                score=-999.0,
                is_selected=False,
                reasons=["closed-question header with short structured answers"],
                non_blank_count=int(len(non_blank)),
                unique_ratio=unique_ratio,
                avg_length=avg_length,
                long_text_ratio=long_text_ratio,
                numeric_ratio=numeric_ratio,
            )

        if self._looks_like_short_text_label_set(
            avg_length=avg_length,
            long_text_ratio=long_text_ratio,
        ):
            if not header_has_open_cue:
                return VerbatimQuestionCandidate(
                    column_name=column_name,
                    score=-999.0,
                    is_selected=False,
                    reasons=["short answers need stronger open-ended question cues"],
                    non_blank_count=int(len(non_blank)),
                    unique_ratio=unique_ratio,
                    avg_length=avg_length,
                    long_text_ratio=long_text_ratio,
                    numeric_ratio=numeric_ratio,
                )
            if unique_count < self.SHORT_TEXT_UNIQUE_COUNT_MIN and top10_coverage > self.SHORT_TEXT_TOP10_COVERAGE_MAX:
                return VerbatimQuestionCandidate(
                    column_name=column_name,
                    score=-999.0,
                    is_selected=False,
                    reasons=["short answers do not show enough open-text variation"],
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
        if (
            non_blank_count >= self.SMALL_SAMPLE_FIXED_RESPONSE_MIN_ROWS
            and top5_coverage >= self.SMALL_SAMPLE_FIXED_RESPONSE_TOP5_COVERAGE_MIN
            and (
                unique_count <= self.SMALL_SAMPLE_FIXED_RESPONSE_UNIQUE_COUNT_MAX
                or unique_ratio <= self.SMALL_SAMPLE_FIXED_RESPONSE_UNIQUE_RATIO_MAX
            )
        ):
            return True

        if non_blank_count < self.MIN_VARIATION_ROW_COUNT:
            return False

        return (
            (unique_count <= self.LOW_VARIATION_UNIQUE_COUNT_MAX and top5_coverage >= self.LOW_VARIATION_TOP5_COVERAGE_MIN)
            or
            (unique_ratio <= self.LOW_VARIATION_UNIQUE_RATIO_MAX and top10_coverage >= self.LOW_VARIATION_TOP10_COVERAGE_MIN)
        )

    def _has_open_ended_header_cue(self, normalized_header: str) -> bool:
        if any(phrase in normalized_header for phrase in self.OPEN_ENDED_HEADER_PHRASES):
            return True
        tokens = set(normalized_header.split())
        return bool(tokens & self.OPEN_ENDED_HEADER_TOKENS)

    def _looks_like_closed_question_header(self, normalized_header: str) -> bool:
        return any(phrase in normalized_header for phrase in self.CLOSED_QUESTION_HEADER_PHRASES)

    def _looks_like_short_text_label_set(
        self,
        *,
        avg_length: float,
        long_text_ratio: float,
    ) -> bool:
        return (
            avg_length <= self.SHORT_TEXT_AVG_LENGTH_MAX
            and long_text_ratio <= self.SHORT_TEXT_LONG_RATIO_MAX
        )

    @staticmethod
    def _normalize_header(column_name: str) -> str:
        base_name = TRANSFORMED_COLUMN_INDEX_SUFFIX_PATTERN.sub("", column_name.strip())
        return re.sub(r"[_\W]+", " ", base_name.casefold()).strip()

    @staticmethod
    def _looks_like_identifier_header(tokens: list[str]) -> bool:
        return MetadataColumnSelectionService._looks_like_identifier_header(tokens)


class AnalysisReadyDatasetService:
    """Builds the final analysis-ready slice from a transformed dataframe."""

    def __init__(
        self,
        metadata_selector: MetadataColumnSelectionService,
        verbatim_selector: VerbatimQuestionSelectionService,
        multipart_verbatim_consolidator: MultipartVerbatimConsolidationService,
        row_filter: VerbatimRowFilterService,
    ) -> None:
        self.metadata_selector = metadata_selector
        self.verbatim_selector = verbatim_selector
        self.multipart_verbatim_consolidator = multipart_verbatim_consolidator
        self.row_filter = row_filter

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

    def build_from_assignments(
        self,
        df: pd.DataFrame,
        *,
        metadata_columns: list[str],
        verbatim_columns: list[str],
    ) -> tuple[pd.DataFrame, list[str], list[str]]:
        if df.empty:
            resolved_metadata = [column for column in metadata_columns if column in df.columns]
            resolved_verbatim = [column for column in verbatim_columns if column in df.columns and column not in set(resolved_metadata)]
            selected_columns = resolved_metadata + resolved_verbatim
            return df[selected_columns].copy(), resolved_metadata, resolved_verbatim

        resolved_metadata = []
        seen_columns: set[str] = set()
        for column in metadata_columns:
            if column in df.columns and column not in seen_columns:
                resolved_metadata.append(column)
                seen_columns.add(column)

        resolved_verbatim = []
        for column in verbatim_columns:
            if column in df.columns and column not in seen_columns:
                resolved_verbatim.append(column)
                seen_columns.add(column)

        selected_columns = resolved_metadata + resolved_verbatim
        analysis_df = df[selected_columns].copy()
        analysis_df = self.row_filter.drop_empty_rows(analysis_df, resolved_verbatim)
        return analysis_df, resolved_metadata, resolved_verbatim


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
            .first()
            .reset_index()
        )
        return grouped


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
