from __future__ import annotations

import base64
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageChops

from app.services.report_export_service._constants import (
    _DATA_URL_PATTERN,
    _PPTX_SLIDE_BACKGROUND_RGB,
)


@dataclass(slots=True)
class DecodedChartImage:
    title: str
    caption: str
    image_bytes: bytes
    width: int
    height: int


class ReportChartImageService:
    def __init__(self, *, sanitize_chart_caption) -> None:
        self.sanitize_chart_caption = sanitize_chart_caption

    def decode_chart(self, chart) -> DecodedChartImage:
        match = _DATA_URL_PATTERN.match(chart.image_data_url.strip())
        if match is None:
            raise ValueError(f"Chart '{chart.title}' does not contain a supported image data URL.")

        image_bytes = base64.b64decode(match.group("data"))
        image = Image.open(BytesIO(image_bytes))
        image.load()
        normalized = BytesIO()
        if image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGB")
        image.save(normalized, format="PNG")
        return DecodedChartImage(
            title=chart.title.strip() or "Chart",
            caption=self.sanitize_chart_caption(chart.caption),
            image_bytes=normalized.getvalue(),
            width=int(image.width),
            height=int(image.height),
        )

    @staticmethod
    def fit_image_to_bounds(*, width: int, height: int, max_width: float, max_height: float) -> tuple[float, float]:
        if width <= 0 or height <= 0:
            return max_width, min(max_height, max_width * 0.6)
        scale = min(max_width / float(width), max_height / float(height))
        return width * scale, height * scale

    def normalize_export_chart_image(self, chart: DecodedChartImage) -> DecodedChartImage:
        image = Image.open(BytesIO(chart.image_bytes)).convert("RGB")
        background_color = image.getpixel((0, 0))
        background = Image.new("RGB", image.size, background_color)
        difference = ImageChops.difference(image, background).convert("L")
        mask = difference.point(lambda value: 255 if value > 8 else 0)
        bbox = mask.getbbox()
        if bbox is None:
            return chart

        padding = 10
        left = max(0, bbox[0] - padding)
        top = max(0, bbox[1] - padding)
        right = min(image.width, bbox[2] + padding)
        bottom = min(image.height, bbox[3] + padding)
        cropped = image.crop((left, top, right, bottom))

        white = Image.new("RGB", cropped.size, _PPTX_SLIDE_BACKGROUND_RGB)
        recolored = cropped.copy()
        pixels = recolored.load()
        for x in range(recolored.width):
            for y in range(recolored.height):
                r, g, b = pixels[x, y]
                if (
                    abs(r - background_color[0]) <= 20
                    and abs(g - background_color[1]) <= 20
                    and abs(b - background_color[2]) <= 20
                ):
                    pixels[x, y] = _PPTX_SLIDE_BACKGROUND_RGB
        cropped = ImageChops.blend(white, recolored, 1.0)

        normalized = BytesIO()
        cropped.save(normalized, format="PNG")
        return DecodedChartImage(
            title=chart.title,
            caption=chart.caption,
            image_bytes=normalized.getvalue(),
            width=int(cropped.width),
            height=int(cropped.height),
        )

    def trim_pptx_chart_image(self, chart: DecodedChartImage) -> DecodedChartImage:
        return self.normalize_export_chart_image(chart)
