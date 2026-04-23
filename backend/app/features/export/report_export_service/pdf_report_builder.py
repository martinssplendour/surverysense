from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image as ReportLabImage,
)
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from app.features.export.report_export_service._constants import _REPORT_TITLE_COLOR
from app.features.export.report_export_service.chart_image import DecodedChartImage


class PdfReportBuilder:
    def __init__(self, *, content_service, chart_image_service) -> None:
        self.content_service = content_service
        self.chart_image_service = chart_image_service

    def build(self, *, request, charts: list[DecodedChartImage]) -> bytes:
        buffer = BytesIO()
        document = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=42,
            rightMargin=42,
            topMargin=42,
            bottomMargin=42,
        )
        styles = self._build_styles()
        story: list[object] = []

        story.append(Paragraph(self.content_service.escape(self.content_service.build_report_title()), styles["title"]))
        story.append(Paragraph(self.content_service.escape(self.content_service.build_subtitle(request)), styles["subtitle"]))
        story.append(Spacer(1, 12))

        if charts:
            for index, chart in enumerate(charts):
                story.append(Paragraph(self.content_service.escape(chart.title), styles["plot_title"]))
                if chart.caption:
                    story.append(Paragraph(self.content_service.escape(chart.caption), styles["plot_caption"]))
                story.append(Spacer(1, 8))
                story.append(self._build_chart_image(chart, max_width=document.width, max_height=320))
                if index < len(charts) - 1:
                    story.append(Spacer(1, 18))
            story.append(PageBreak())

        story.append(Paragraph(self.content_service.build_summary_heading(request), styles["section"]))
        story.append(Spacer(1, 8))
        group_sections = self.content_service.build_group_summary_sections(request)
        if group_sections:
            for section in group_sections[:8]:
                story.append(Paragraph(self.content_service.escape(section.label), styles["chart_title"]))
                story.append(Paragraph(self.content_service.escape(section.summary), styles["body"]))
                story.append(Spacer(1, 6))
        else:
            for line in self.content_service.build_summary_lines(request):
                story.append(Paragraph(f"&#8226; {self.content_service.escape(line)}", styles["body"]))
                story.append(Spacer(1, 5))

        representative_sections = self.content_service.build_representative_sections(request)
        if representative_sections:
            story.append(Spacer(1, 10))
            story.append(Paragraph(self.content_service.build_representative_heading(), styles["section"]))
            story.append(Spacer(1, 8))
            for label, examples in representative_sections:
                story.append(Paragraph(self.content_service.escape(label), styles["chart_title"]))
                for index, example in enumerate(examples, start=1):
                    story.append(Paragraph(f"{index}. {self.content_service.escape(example)}", styles["body"]))
                    story.append(Spacer(1, 4))
                story.append(Spacer(1, 8))

        document.build(story, onFirstPage=self._decorate_page, onLaterPages=self._decorate_page)
        return buffer.getvalue()

    def _build_styles(self) -> dict[str, ParagraphStyle]:
        base = getSampleStyleSheet()
        return {
            "title": ParagraphStyle(
                "ReportTitle",
                parent=base["Title"],
                fontName="Helvetica-Bold",
                fontSize=22,
                leading=26,
                textColor=colors.HexColor(_REPORT_TITLE_COLOR),
                alignment=TA_LEFT,
                spaceAfter=6,
            ),
            "subtitle": ParagraphStyle(
                "ReportSubtitle",
                parent=base["BodyText"],
                fontName="Helvetica",
                fontSize=10,
                leading=14,
                textColor=colors.HexColor("#5e574f"),
                spaceAfter=0,
            ),
            "section": ParagraphStyle(
                "ReportSection",
                parent=base["Heading2"],
                fontName="Helvetica-Bold",
                fontSize=14,
                textColor=colors.HexColor("#294b3b"),
                spaceAfter=4,
            ),
            "chart_title": ParagraphStyle(
                "ReportChartTitle",
                parent=base["Heading3"],
                fontName="Helvetica-Bold",
                fontSize=11,
                textColor=colors.HexColor("#3d352d"),
                spaceAfter=2,
            ),
            "plot_title": ParagraphStyle(
                "ReportPlotTitle",
                parent=base["Heading3"],
                fontName="Helvetica-Bold",
                fontSize=11,
                textColor=colors.HexColor("#3d352d"),
                spaceAfter=2,
            ),
            "plot_caption": ParagraphStyle(
                "ReportPlotCaption",
                parent=base["BodyText"],
                fontName="Helvetica-Oblique",
                fontSize=9,
                leading=12,
                textColor=colors.HexColor("#6d655b"),
                spaceAfter=6,
            ),
            "body": ParagraphStyle(
                "ReportBody",
                parent=base["BodyText"],
                fontName="Helvetica",
                fontSize=10,
                leading=14,
                textColor=colors.HexColor("#3d352d"),
            ),
        }

    def _build_chart_image(self, chart: DecodedChartImage, *, max_width: float, max_height: float) -> ReportLabImage:
        width_inches, height_inches = self.chart_image_service.fit_image_to_bounds(
            width=chart.width,
            height=chart.height,
            max_width=max_width / inch,
            max_height=max_height / inch,
        )
        return ReportLabImage(BytesIO(chart.image_bytes), width=width_inches * inch, height=height_inches * inch)

    @staticmethod
    def _decorate_page(canvas, document) -> None:
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#d8cdbf"))
        canvas.setFillColor(colors.HexColor("#294b3b"))
        canvas.setFont("Helvetica", 9)
        canvas.drawRightString(document.pagesize[0] - 42, 20, f"Page {document.page}")
        canvas.restoreState()
