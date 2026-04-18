from __future__ import annotations

import re

import pandas as pd


class ManifestHeaderScoringService:
    @staticmethod
    def score_wide_verbatim_column(series: pd.Series, header_name: str) -> float:
        non_blank = series[series.notna() & (series.astype(str).str.strip() != "")]
        if non_blank.empty:
            return 0.0

        text_values = non_blank.astype(str).str.strip()
        unique_ratio = text_values.nunique(dropna=True) / max(len(text_values), 1)
        avg_length = text_values.str.len().mean()
        long_text_ratio = (text_values.str.len() >= 20).mean()
        numeric_ratio = pd.to_numeric(text_values, errors="coerce").notna().mean()

        score = 0.0
        if avg_length >= 12:
            score += 1.0
        if long_text_ratio >= 0.25:
            score += 1.0
        if unique_ratio >= 0.4:
            score += 1.0
        if numeric_ratio <= 0.25:
            score += 1.0
        score += ManifestHeaderScoringService.header_hint_score(
            header_name,
            {"answer", "response", "comment", "feedback", "verbatim", "text"},
        )
        return score

    @staticmethod
    def score_question_header_column(series: pd.Series, header_name: str) -> float:
        non_blank = series[series.notna() & (series.astype(str).str.strip() != "")]
        if non_blank.empty:
            return 0.0

        text_values = non_blank.astype(str).str.strip()
        avg_length = text_values.str.len().mean()
        score = 0.0
        if avg_length >= 8:
            score += 1.0
        if avg_length >= 20:
            score += 0.5

        return score + ManifestHeaderScoringService.question_header_name_score(header_name)

    @staticmethod
    def question_header_name_score(header_name: str) -> float:
        normalized_header = header_name.strip().casefold()
        score = 0.0
        if "survey_title" in normalized_header or normalized_header in {"survey name", "survey_name"}:
            score -= 3.0
        if "full_title" in normalized_header:
            score += 2.5
        if "main_title" in normalized_header:
            score += 1.75
        if "sub_title" in normalized_header:
            score += 1.25
        if any(token in normalized_header for token in {"question_text", "question", "prompt", "item", "topic"}):
            score += 1.0
        return score

    @staticmethod
    def record_key_header_score(header_name: str) -> float:
        tokens = ManifestHeaderScoringService.header_tokens(header_name)
        score = 0.0
        if "id" in tokens:
            score += 1.0
        if {"response", "id"} <= tokens:
            score += 1.5
        if {"user", "id"} <= tokens:
            score += 1.0
        if {"record", "id"} <= tokens or {"submission", "id"} <= tokens:
            score += 1.0
        if "respondent" in tokens:
            score += 0.75
        return score

    @staticmethod
    def answer_header_score(header_name: str) -> float:
        tokens = ManifestHeaderScoringService.header_tokens(header_name)
        score = 0.0
        if "answer" in tokens:
            score += 1.0
        if "value" in tokens:
            score += 0.75
        if "response" in tokens and "id" not in tokens:
            score += 0.5
        if tokens & {"comment", "comments", "feedback", "verbatim", "text"}:
            score += 1.0
        if "id" in tokens:
            score -= 1.0
        return score

    @staticmethod
    def helper_header_penalty(header_name: str) -> float:
        tokens = ManifestHeaderScoringService.header_tokens(header_name)
        return 1.0 if tokens & {"order", "sequence", "number", "code", "rank", "position"} else 0.0

    @staticmethod
    def header_tokens(header_name: str) -> set[str]:
        return {token for token in re.split(r"[_\W]+", header_name.casefold()) if token}

    @staticmethod
    def identifier_like_ratio(series: pd.Series) -> float:
        if series.empty:
            return 0.0
        text = series.astype(str).str.strip()
        nonempty = text != ""
        no_space = ~text.str.contains(" ", regex=False, na=False)
        pattern_hit = text.str.fullmatch(r"[0-9a-f]{6,}(?:-[0-9a-f]{2,}){2,}", case=False, na=False)
        long_enough = text.str.len() >= 12
        has_digit = text.str.contains(r"\d", regex=True, na=False)
        has_alpha = text.str.contains(r"[a-zA-Z]", regex=True, na=False)
        has_dash = text.str.count(r"-") >= 1
        fallback = no_space & long_enough & has_digit & has_alpha & has_dash
        is_identifier = nonempty & no_space & (pattern_hit | fallback)
        return float(is_identifier.mean())

    @staticmethod
    def header_hint_score(header_name: str, tokens: set[str]) -> float:
        normalized = header_name.strip().casefold()
        return 1.0 if any(token in normalized for token in tokens) else 0.0
