from __future__ import annotations

import re

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
