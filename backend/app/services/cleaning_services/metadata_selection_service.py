from __future__ import annotations

import re

import pandas as pd

from app.services.cleaning_services._patterns import TRANSFORMED_COLUMN_INDEX_SUFFIX_PATTERN


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
