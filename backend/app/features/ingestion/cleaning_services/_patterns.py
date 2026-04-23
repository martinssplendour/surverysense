"""Shared compiled regex patterns used across the cleaning pipeline."""
from __future__ import annotations

import re

# Matches curly/backtick/prime apostrophe variants so they can be normalised to a straight apostrophe.
SMART_APOSTROPHES_PATTERN = re.compile(r"[\u2018\u2019\u0060\u00B4\u2032\u0092]")
# Strips leading question-number prefixes such as "1.", "2.3)", "Q1:" from column headers.
NUMERIC_HEADER_PREFIX_PATTERN = re.compile(r"^\s*\d+(?:\.\d+)*\s*[:.)-]\s*")
# Strips the __idx_N suffix appended by the transformation pipeline to disambiguate duplicate headers.
TRANSFORMED_COLUMN_INDEX_SUFFIX_PATTERN = re.compile(r"__idx_\d+$", re.IGNORECASE)
# Each pattern matches "Base Question: Word 1", "Base - Answer 2", "Base (Part 3)" style headers.
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
