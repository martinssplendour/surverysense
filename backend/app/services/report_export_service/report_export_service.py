from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from io import BytesIO
from types import SimpleNamespace

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches as DocxInches
from docx.shared import Pt as DocxPt
from docx.shared import RGBColor
from PIL import Image, ImageChops
from pptx import Presentation
from pptx.dml.color import RGBColor as PptxRGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches as PptxInches
from pptx.util import Pt as PptxPt
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image as ReportLabImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from app.models.api import AnalysisExportChartModel, AnalysisExportRequest
from app.services.report_export_service._constants import (
    _DATA_URL_PATTERN,
    _FILENAME_PATTERN,
    _PPTX_CONTENT_LEFT,
    _PPTX_CONTENT_WIDTH,
    _PPTX_DETAIL_RGB,
    _PPTX_SLIDE_BACKGROUND_RGB,
    _PPTX_SLIDE_HEIGHT,
    _PPTX_TEXT_RGB,
    _REPORT_TITLE_COLOR,
    _REPORT_TITLE_RGB,
)


@dataclass(slots=True)
class ExportedReportArtifact:
    filename: str
    media_type: str
    content: bytes


@dataclass(slots=True)
class DecodedChartImage:
    title: str
    caption: str
    image_bytes: bytes
    width: int
    height: int


@dataclass(slots=True)
class GroupSummarySection:
    label: str
    summary: str
    examples: list[str]


class AnalysisReportExportService:
    def __init__(self, result_store_service=None) -> None:
        self.result_store_service = result_store_service

    def export_report(self, *, result_id: str, request: AnalysisExportRequest) -> ExportedReportArtifact:
        if request.analysis_result.result_id != result_id:
            raise ValueError("The report payload does not match the requested analysis result.")

        charts = [self._normalize_export_chart_image(self._decode_chart(chart)) for chart in request.charts]
        content: bytes
        media_type: str
        extension = request.format

        if request.format == "pdf":
            content = self._build_pdf(request=request, charts=charts)
            media_type = "application/pdf"
        elif request.format == "docx":
            content = self._build_docx(request=request, charts=charts)
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            content = self._build_pptx(request=request, charts=charts)
            media_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

        stem = self._slugify(self._build_filename_stem(request))
        return ExportedReportArtifact(
            filename=f"{stem}.{extension}",
            media_type=media_type,
            content=content,
        )

    def _build_pdf(self, *, request: AnalysisExportRequest, charts: list[DecodedChartImage]) -> bytes:
        buffer = BytesIO()
        document = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=42,
            rightMargin=42,
            topMargin=42,
            bottomMargin=42,
        )
        styles = self._build_pdf_styles()
        story: list[object] = []

        story.append(Paragraph(self._escape(self._build_report_title()), styles["title"]))
        story.append(Paragraph(self._escape(self._build_subtitle(request)), styles["subtitle"]))
        story.append(Spacer(1, 12))

        if charts:
            for index, chart in enumerate(charts):
                story.append(Paragraph(self._escape(chart.title), styles["plot_title"]))
                if chart.caption:
                    story.append(Paragraph(self._escape(chart.caption), styles["plot_caption"]))
                story.append(Spacer(1, 8))
                story.append(self._build_pdf_chart_image(chart, max_width=document.width, max_height=320))
                if index < len(charts) - 1:
                    story.append(Spacer(1, 18))
            story.append(PageBreak())

        story.append(Paragraph(self._build_summary_heading(request), styles["section"]))
        story.append(Spacer(1, 8))
        group_sections = self._build_group_summary_sections(request)
        if group_sections:
            for section in group_sections[:8]:
                story.append(Paragraph(self._escape(section.label), styles["chart_title"]))
                story.append(Paragraph(self._escape(section.summary), styles["body"]))
                story.append(Spacer(1, 6))
        else:
            for line in self._build_summary_lines(request):
                story.append(Paragraph(f"&#8226; {self._escape(line)}", styles["body"]))
                story.append(Spacer(1, 5))

        representative_sections = self._build_representative_sections(request)
        if representative_sections:
            story.append(Spacer(1, 10))
            story.append(Paragraph(self._build_representative_heading(), styles["section"]))
            story.append(Spacer(1, 8))
            for label, examples in representative_sections:
                story.append(Paragraph(self._escape(label), styles["chart_title"]))
                for index, example in enumerate(examples, start=1):
                    story.append(Paragraph(f"{index}. {self._escape(example)}", styles["body"]))
                    story.append(Spacer(1, 4))
                story.append(Spacer(1, 8))

        document.build(story, onFirstPage=self._decorate_pdf_page, onLaterPages=self._decorate_pdf_page)
        return buffer.getvalue()

    def _build_docx(self, *, request: AnalysisExportRequest, charts: list[DecodedChartImage]) -> bytes:
        document = Document()
        section = document.sections[0]
        section.top_margin = DocxInches(0.55)
        section.bottom_margin = DocxInches(0.55)
        section.left_margin = DocxInches(0.65)
        section.right_margin = DocxInches(0.65)

        title = document.add_paragraph()
        title.style = document.styles["Title"]
        title.alignment = WD_ALIGN_PARAGRAPH.LEFT
        title_run = title.add_run(self._build_report_title())
        title_run.font.name = "Aptos Display"
        title_run.font.size = DocxPt(22)
        title_run.font.color.rgb = RGBColor(*_REPORT_TITLE_RGB)

        metadata = document.add_paragraph(self._build_subtitle(request))
        metadata.style = document.styles["Subtitle"]
        for run in metadata.runs:
            run.font.name = "Aptos"
            run.font.size = DocxPt(10)

        document.add_paragraph()

        if charts:
            for chart in charts:
                heading = document.add_paragraph()
                heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
                heading_run = heading.add_run(chart.title)
                heading_run.bold = True
                heading_run.font.name = "Aptos Display"
                heading_run.font.size = DocxPt(14)
                heading_run.font.color.rgb = RGBColor(*_REPORT_TITLE_RGB)
                if chart.caption:
                    caption = document.add_paragraph(chart.caption)
                    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    for run in caption.runs:
                        run.italic = True
                        run.font.name = "Aptos"
                        run.font.size = DocxPt(9)
                        run.font.color.rgb = RGBColor(98, 91, 82)
                image_paragraph = document.add_paragraph()
                image_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                image_paragraph.add_run().add_picture(BytesIO(chart.image_bytes), width=DocxInches(6.45))

        document.add_heading(self._build_summary_heading(request), level=1)
        group_sections = self._build_group_summary_sections(request)
        if group_sections:
            for section in group_sections[:8]:
                heading = document.add_paragraph()
                heading_run = heading.add_run(section.label)
                heading_run.bold = True
                heading_run.font.name = "Aptos"
                heading_run.font.size = DocxPt(11)

                paragraph = document.add_paragraph()
                run = paragraph.add_run(section.summary)
                run.font.name = "Aptos"
                run.font.size = DocxPt(10)
        else:
            for line in self._build_summary_lines(request):
                paragraph = document.add_paragraph()
                run = paragraph.add_run(line)
                run.font.name = "Aptos"
                run.font.size = DocxPt(10)

        representative_sections = self._build_representative_sections(request)
        if representative_sections:
            document.add_heading(self._build_representative_heading(), level=1)
            for label, examples in representative_sections:
                group_heading = document.add_paragraph()
                group_run = group_heading.add_run(label)
                group_run.bold = True
                group_run.font.name = "Aptos"
                group_run.font.size = DocxPt(11)
                for index, example in enumerate(examples, start=1):
                    paragraph = document.add_paragraph()
                    run = paragraph.add_run(f"{index}. {example}")
                    run.font.name = "Aptos"
                    run.font.size = DocxPt(10)

        output = BytesIO()
        document.save(output)
        return output.getvalue()

    def _build_pptx(self, *, request: AnalysisExportRequest, charts: list[DecodedChartImage]) -> bytes:
        presentation = Presentation()
        self._build_pptx_title_slide(presentation, request)

        for chart in charts:
            self._build_pptx_chart_slide(presentation, chart)

        self._build_pptx_summary_slide(presentation, request)
        self._build_pptx_representative_slides(presentation, request)

        output = BytesIO()
        presentation.save(output)
        return output.getvalue()

    def _build_pptx_title_slide(self, presentation: Presentation, request: AnalysisExportRequest) -> None:
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        self._set_pptx_slide_background(slide)

        title_top = 3.3
        subtitle_top = 4.02
        title_box_width = _PPTX_CONTENT_WIDTH * 0.76
        title_box_left = _PPTX_CONTENT_LEFT

        title_box = slide.shapes.add_textbox(
            PptxInches(title_box_left),
            PptxInches(title_top),
            PptxInches(title_box_width),
            PptxInches(0.7),
        )
        title_frame = title_box.text_frame
        title_frame.clear()
        title_paragraph = title_frame.paragraphs[0]
        title_paragraph.text = self._build_report_title()
        title_paragraph.font.size = PptxPt(26)
        title_paragraph.font.bold = True
        title_paragraph.font.color.rgb = PptxRGBColor(*_PPTX_TEXT_RGB)
        title_paragraph.alignment = PP_ALIGN.LEFT

        subtitle_box = slide.shapes.add_textbox(
            PptxInches(title_box_left),
            PptxInches(subtitle_top),
            PptxInches(title_box_width),
            PptxInches(0.68),
        )
        subtitle_frame = subtitle_box.text_frame
        subtitle_frame.clear()
        subtitle_frame.word_wrap = True
        subtitle_paragraph = subtitle_frame.paragraphs[0]
        subtitle_paragraph.text = self._build_subtitle(request)
        subtitle_paragraph.font.size = PptxPt(10)
        subtitle_paragraph.font.color.rgb = PptxRGBColor(*_PPTX_DETAIL_RGB)
        subtitle_paragraph.alignment = PP_ALIGN.LEFT

    def _build_pptx_chart_slide(self, presentation: Presentation, chart: DecodedChartImage) -> None:
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        self._set_pptx_slide_background(slide)
        self._add_pptx_slide_title(slide, chart.title)

        content_top = 1.0
        if chart.caption:
            caption_box = slide.shapes.add_textbox(
                PptxInches(_PPTX_CONTENT_LEFT),
                PptxInches(1.02),
                PptxInches(_PPTX_CONTENT_WIDTH),
                PptxInches(0.4),
            )
            caption_frame = caption_box.text_frame
            caption_frame.paragraphs[0].text = chart.caption
            caption_frame.paragraphs[0].font.size = PptxPt(10)
            caption_frame.paragraphs[0].font.color.rgb = PptxRGBColor(*_PPTX_DETAIL_RGB)
            caption_frame.paragraphs[0].alignment = PP_ALIGN.LEFT
            content_top = 1.42

        image = Image.open(BytesIO(chart.image_bytes))
        target_max_width = _PPTX_CONTENT_WIDTH * 0.8
        width_inches, height_inches = self._fit_image_to_bounds(
            width=image.width,
            height=image.height,
            max_width=target_max_width,
            max_height=_PPTX_SLIDE_HEIGHT - content_top - 0.45,
        )
        width_inches *= 0.9
        height_inches *= 0.9
        left = max(0.25, _PPTX_CONTENT_LEFT - 0.12)
        top = max(content_top, (_PPTX_SLIDE_HEIGHT - height_inches) / 2)
        slide.shapes.add_picture(
            BytesIO(chart.image_bytes),
            PptxInches(left),
            PptxInches(top),
            width=PptxInches(width_inches),
            height=PptxInches(height_inches),
        )

    def _build_pptx_summary_slide(self, presentation: Presentation, request: AnalysisExportRequest) -> None:
        summary_box_width = _PPTX_CONTENT_WIDTH * 0.7
        summary_box_left = _PPTX_CONTENT_LEFT
        group_sections = self._build_group_summary_sections(request)
        if group_sections:
            for chunk_start in range(0, min(len(group_sections), 8), 4):
                slide = presentation.slides.add_slide(presentation.slide_layouts[6])
                self._set_pptx_slide_background(slide)
                title = self._build_summary_heading(request)
                if chunk_start > 0:
                    title = f"{title} (continued)"
                self._add_pptx_slide_title(slide, title)

                top = 1.2
                for section in group_sections[chunk_start:chunk_start + 4]:
                    box = slide.shapes.add_textbox(
                        PptxInches(summary_box_left),
                        PptxInches(top),
                        PptxInches(summary_box_width),
                        PptxInches(1.25),
                    )
                    frame = box.text_frame
                    frame.clear()
                    frame.word_wrap = True

                    heading = frame.paragraphs[0]
                    heading.text = section.label
                    heading.font.size = PptxPt(16)
                    heading.font.bold = True
                    heading.font.color.rgb = PptxRGBColor(*_PPTX_TEXT_RGB)
                    heading.alignment = PP_ALIGN.LEFT

                    paragraph = frame.add_paragraph()
                    paragraph.text = section.summary
                    paragraph.font.size = PptxPt(12)
                    paragraph.font.color.rgb = PptxRGBColor(*_PPTX_DETAIL_RGB)
                    paragraph.alignment = PP_ALIGN.LEFT
                    paragraph.space_after = PptxPt(6)
                    top += 1.35
            return

        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        self._set_pptx_slide_background(slide)
        self._add_pptx_slide_title(slide, self._build_summary_heading(request))

        box = slide.shapes.add_textbox(
            PptxInches(summary_box_left),
            PptxInches(1.35),
            PptxInches(summary_box_width),
            PptxInches(5.6),
        )
        frame = box.text_frame
        frame.word_wrap = True
        findings = self._build_summary_lines(request)[:8]
        for index, line in enumerate(findings):
            paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
            paragraph.text = line
            paragraph.level = 0
            paragraph.bullet = True
            paragraph.font.size = PptxPt(14)
            paragraph.font.color.rgb = PptxRGBColor(*_PPTX_DETAIL_RGB)
            paragraph.alignment = PP_ALIGN.LEFT
            paragraph.space_after = PptxPt(8)

    def _build_pptx_representative_slides(self, presentation: Presentation, request: AnalysisExportRequest) -> None:
        sections = self._build_representative_sections(request)
        if not sections:
            return

        for chunk_start in range(0, len(sections), 2):
            slide = presentation.slides.add_slide(presentation.slide_layouts[6])
            self._set_pptx_slide_background(slide)
            self._add_pptx_slide_title(slide, self._build_representative_heading())

            top = 1.25
            group_box_width = _PPTX_CONTENT_WIDTH * 0.7
            group_box_left = _PPTX_CONTENT_LEFT
            for label, examples in sections[chunk_start:chunk_start + 2]:
                group_box = slide.shapes.add_textbox(
                    PptxInches(group_box_left),
                    PptxInches(top),
                    PptxInches(group_box_width),
                    PptxInches(2.65),
                )
                frame = group_box.text_frame
                frame.clear()
                frame.word_wrap = True

                heading = frame.paragraphs[0]
                heading.text = label
                heading.font.size = PptxPt(16)
                heading.font.bold = True
                heading.font.color.rgb = PptxRGBColor(*_PPTX_TEXT_RGB)
                heading.alignment = PP_ALIGN.LEFT

                for index, example in enumerate(examples, start=1):
                    paragraph = frame.add_paragraph()
                    paragraph.text = f"{index}. {example}"
                    paragraph.font.size = PptxPt(12)
                    paragraph.font.color.rgb = PptxRGBColor(*_PPTX_DETAIL_RGB)
                    paragraph.alignment = PP_ALIGN.LEFT
                    paragraph.space_after = PptxPt(6)
                top += 2.8

    def _build_pdf_styles(self) -> dict[str, ParagraphStyle]:
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
                fontSize=14,
                textColor=colors.HexColor(_REPORT_TITLE_COLOR),
                alignment=TA_LEFT,
                spaceAfter=2,
            ),
            "plot_caption": ParagraphStyle(
                "ReportPlotCaption",
                parent=base["BodyText"],
                fontName="Helvetica-Oblique",
                fontSize=9,
                leading=12,
                textColor=colors.HexColor("#6d655b"),
                alignment=TA_LEFT,
                spaceAfter=0,
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

    def _build_pdf_chart_image(self, chart: DecodedChartImage, *, max_width: float, max_height: float) -> ReportLabImage:
        width_inches, height_inches = self._fit_image_to_bounds(
            width=chart.width,
            height=chart.height,
            max_width=max_width / inch,
            max_height=max_height / inch,
        )
        return ReportLabImage(BytesIO(chart.image_bytes), width=width_inches * inch, height=height_inches * inch)

    def _decorate_pdf_page(self, canvas, document) -> None:
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#d8cdbf"))
        canvas.setFillColor(colors.HexColor("#294b3b"))
        canvas.setFont("Helvetica", 9)
        canvas.drawRightString(document.pagesize[0] - 42, 20, f"Page {document.page}")
        canvas.restoreState()

    def _build_summary_lines(self, request: AnalysisExportRequest) -> list[str]:
        result = request.analysis_result
        if result.ngram_buckets:
            findings: list[str] = []
            for bucket in result.ngram_buckets:
                top_items = bucket.items[:5]
                if not top_items:
                    continue
                lines = ", ".join(
                    f"{item.term} ({item.document_count} responses)"
                    for item in top_items
                )
                findings.append(f"{bucket.label}: {lines}")
            return findings or ["No phrase-level findings were available for export."]

        group_sections = self._build_group_summary_sections(request)
        if group_sections:
            return [f"{section.label}: {section.summary}" for section in group_sections[:8]]

        return ["The selected analysis completed without exportable topic findings."]

    def _build_group_summary_sections(self, request: AnalysisExportRequest) -> list[GroupSummarySection]:
        groups = self._get_export_groups(request)
        if not groups:
            return []

        sections: list[GroupSummarySection] = []
        ordered_groups = sorted(groups, key=lambda group: (-group.count, group.label))
        for group in ordered_groups:
            share_pct = round(group.share * 100)
            terms = ", ".join(group.terms[:4]) if group.terms else "no top terms available"
            examples = [
                self._truncate_text(" ".join(example.text.split()), limit=240)
                for example in group.examples[:3]
                if example.text.strip()
            ]
            sections.append(
                GroupSummarySection(
                    label=group.label,
                    summary=f"{group.count} responses ({share_pct}%). Top terms: {terms}.",
                    examples=examples,
                )
            )
        return sections

    def _get_export_groups(self, request: AnalysisExportRequest):
        if self.result_store_service is not None:
            try:
                fast_result = self.result_store_service.get_fast_filtered_result(
                    request.analysis_result.result_id,
                    model_key=request.analysis_result.model_key,
                    text_column_name=request.analysis_result.text_column_name,
                    filters=self._build_active_filter_lookup(request),
                )
            except Exception:
                fast_result = None
            if fast_result and fast_result.get("groups"):
                return [
                    SimpleNamespace(
                        label=str(group.get("label", "")),
                        count=int(group.get("count", 0) or 0),
                        share=float(group.get("share", 0) or 0),
                        terms=list(group.get("terms", [])),
                        examples=[
                            SimpleNamespace(
                                row_number=int(example.get("row_number", 0) or 0),
                                text=str(example.get("text", "")),
                            )
                            for example in group.get("examples", [])
                            if isinstance(example, dict)
                        ],
                    )
                    for group in fast_result.get("groups", [])
                    if isinstance(group, dict)
                ]
        return request.analysis_result.groups

    def _build_active_filter_lookup(self, request: AnalysisExportRequest) -> dict[str, list[str]]:
        return {
            item.column_name: list(item.values)
            for item in request.active_filters
            if item.values
        }

    def _build_subtitle(self, request: AnalysisExportRequest) -> str:
        parts = [self._display_column_label(request.analysis_result.text_column_name)]
        filters_text = self._filters_text(request)
        if filters_text:
            parts.append(filters_text)
        parts.append(self._row_count_text(request))
        return " | ".join(part for part in parts if part)

    def _build_report_title(self) -> str:
        return "Verbatim Analysis Report"

    def _build_summary_heading(self, request: AnalysisExportRequest) -> str:
        if request.analysis_result.ngram_buckets:
            return "Phrase summaries"
        return "Topic summaries"

    def _build_representative_heading(self) -> str:
        return "Representative documents (topics and top 3 responses)"

    def _build_representative_sections(self, request: AnalysisExportRequest) -> list[tuple[str, list[str]]]:
        if request.analysis_result.ngram_buckets:
            return self._build_ngram_representative_sections(request)
        return [
            (section.label, section.examples)
            for section in self._build_group_summary_sections(request)
            if section.examples
        ]

    def _build_ngram_representative_sections(self, request: AnalysisExportRequest) -> list[tuple[str, list[str]]]:
        if self.result_store_service is None:
            return []

        sections: list[tuple[str, list[str]]] = []
        for bucket in request.analysis_result.ngram_buckets[:3]:
            items = list(bucket.items[:5]) if bucket.items else []
            if not items:
                continue

            selected_item = None
            examples: list[str] = []
            for item in items:
                lookup_term = (item.source_term or item.term or "").strip()
                if not lookup_term:
                    continue
                try:
                    page = self.result_store_service.get_analysis_ngram_page(
                        request.analysis_result.result_id,
                        ngram_size=int(bucket.ngram_size),
                        term=lookup_term,
                        offset=0,
                        limit=3,
                    )
                except Exception:
                    continue

                documents = getattr(page, "documents", []) or []
                examples = [
                    self._truncate_text(" ".join(str(document.get("text", "")).split()), limit=240)
                    for document in documents
                    if str(document.get("text", "")).strip()
                ]
                if examples:
                    selected_item = item
                    break

            if selected_item and examples:
                sections.append((f"{bucket.label}: {selected_item.term}", examples))
        return sections

    def _build_filename_stem(self, request: AnalysisExportRequest) -> str:
        source_stem = self._strip_extension(request.source_filename or "analysis")
        method = request.analysis_result.model_label.lower().replace(" ", "-")
        return f"{source_stem}-{method}-report"

    def _filters_text(self, request: AnalysisExportRequest) -> str:
        if not request.active_filters:
            return ""
        return " | ".join(
            f"{item.display_name or item.column_name}: {', '.join(item.values)}"
            for item in request.active_filters
            if item.values
        )

    def _row_count_text(self, request: AnalysisExportRequest) -> str:
        return f"{int(request.analysis_result.filtered_row_count)} rows"

    def _decode_chart(self, chart: AnalysisExportChartModel) -> DecodedChartImage:
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
            caption=self._sanitize_chart_caption(chart.caption),
            image_bytes=normalized.getvalue(),
            width=int(image.width),
            height=int(image.height),
        )

    def _fit_image_to_bounds(self, *, width: int, height: int, max_width: float, max_height: float) -> tuple[float, float]:
        if width <= 0 or height <= 0:
            return max_width, min(max_height, max_width * 0.6)
        scale = min(max_width / float(width), max_height / float(height))
        return width * scale, height * scale

    def _display_column_label(self, value: str) -> str:
        return re.sub(r"__idx_\d+$", "", value or "")

    def _strip_extension(self, filename: str) -> str:
        value = (filename or "").strip()
        if "." not in value:
            return value
        return value.rsplit(".", 1)[0]

    def _slugify(self, value: str) -> str:
        lowered = value.strip().lower()
        normalized = _FILENAME_PATTERN.sub("-", lowered).strip("-")
        return normalized or "analysis-report"

    def _escape(self, value: str) -> str:
        return (
            str(value)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    def _truncate_text(self, value: str, *, limit: int) -> str:
        normalized = " ".join((value or "").split())
        if len(normalized) <= limit:
            return normalized
        return normalized[: max(0, limit - 3)].rstrip() + "..."

    def _sanitize_chart_caption(self, value: str | None) -> str:
        caption = " ".join((value or "").split())
        lower_caption = caption.casefold()
        interactive_phrases = (
            "hover to see",
            "click a bar",
            "matching responses",
            "matching groups responses",
            "matching topics responses",
        )
        if any(phrase in lower_caption for phrase in interactive_phrases):
            return ""
        return caption

    def _normalize_export_chart_image(self, chart: DecodedChartImage) -> DecodedChartImage:
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

    def _trim_pptx_chart_image(self, chart: DecodedChartImage) -> DecodedChartImage:
        return self._normalize_export_chart_image(chart)

    def _set_pptx_slide_background(self, slide) -> None:
        background = slide.background.fill
        background.solid()
        background.fore_color.rgb = PptxRGBColor(*_PPTX_SLIDE_BACKGROUND_RGB)

    def _add_pptx_slide_title(self, slide, title: str) -> None:
        title_box = slide.shapes.add_textbox(
            PptxInches(_PPTX_CONTENT_LEFT),
            PptxInches(0.45),
            PptxInches(_PPTX_CONTENT_WIDTH),
            PptxInches(0.55),
        )
        title_frame = title_box.text_frame
        title_frame.clear()
        paragraph = title_frame.paragraphs[0]
        paragraph.text = title
        paragraph.font.size = PptxPt(20)
        paragraph.font.bold = True
        paragraph.font.color.rgb = PptxRGBColor(*_PPTX_TEXT_RGB)
        paragraph.alignment = PP_ALIGN.LEFT
