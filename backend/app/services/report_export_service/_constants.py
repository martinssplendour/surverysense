from __future__ import annotations

import re

_DATA_URL_PATTERN = re.compile(r"^data:image/(?P<kind>[a-zA-Z0-9.+-]+);base64,(?P<data>.+)$")
_FILENAME_PATTERN = re.compile(r"[^a-z0-9]+")
_REPORT_TITLE_COLOR = "#2a3f5f"
_REPORT_TITLE_RGB = (42, 63, 95)
_PPTX_SLIDE_WIDTH = 13.333
_PPTX_SLIDE_HEIGHT = 7.5
_PPTX_SLIDE_BACKGROUND_RGB = (255, 255, 255)
_PPTX_TEXT_RGB = (93, 134, 211)
_PPTX_DETAIL_RGB = (0, 0, 0)
_PPTX_CONTENT_LEFT = 0.45
_PPTX_CONTENT_WIDTH = _PPTX_SLIDE_WIDTH - (_PPTX_CONTENT_LEFT * 2)
