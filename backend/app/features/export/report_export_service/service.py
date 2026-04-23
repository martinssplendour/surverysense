from __future__ import annotations

from dataclasses import dataclass

from app.models.api import AnalysisExportChartModel, AnalysisExportRequest
from app.features.export.report_export_service.chart_image import (
    DecodedChartImage,
    ReportChartImageService,
)
from app.features.export.report_export_service.docx_report_builder import DocxReportBuilder
from app.features.export.report_export_service.pdf_report_builder import PdfReportBuilder
from app.features.export.report_export_service.pptx_report_builder import PptxReportBuilder
from app.features.export.report_export_service.content import (
    GroupSummarySection,
    ReportContentService,
)
from app.features.common.protocols import ResultStoreReportReaderProtocol


@dataclass(slots=True)
class ExportedReportArtifact:
    filename: str
    media_type: str
    content: bytes


class AnalysisReportExportService:
    def __init__(self, result_store_service: ResultStoreReportReaderProtocol | None = None) -> None:
        self.result_store_service = result_store_service
        self.content_service = ReportContentService(result_store_service=result_store_service)
        self.chart_image_service = ReportChartImageService(
            sanitize_chart_caption=self.content_service.sanitize_chart_caption,
        )
        self.pdf_builder = PdfReportBuilder(
            content_service=self.content_service,
            chart_image_service=self.chart_image_service,
        )
        self.docx_builder = DocxReportBuilder(content_service=self.content_service)
        self.pptx_builder = PptxReportBuilder(
            content_service=self.content_service,
            chart_image_service=self.chart_image_service,
        )

    def export_report(self, *, result_id: str, request: AnalysisExportRequest) -> ExportedReportArtifact:
        if request.analysis_result.result_id != result_id:
            raise ValueError("The report payload does not match the requested analysis result.")

        charts = [
            self._normalize_export_chart_image(self._decode_chart(chart))
            for chart in request.charts
        ]
        if request.format == "pdf":
            content = self.pdf_builder.build(request=request, charts=charts)
            media_type = "application/pdf"
        elif request.format == "docx":
            content = self.docx_builder.build(request=request, charts=charts)
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            content = self.pptx_builder.build(request=request, charts=charts)
            media_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

        stem = self._slugify(self._build_filename_stem(request))
        return ExportedReportArtifact(
            filename=f"{stem}.{request.format}",
            media_type=media_type,
            content=content,
        )

    def _build_summary_lines(self, request: AnalysisExportRequest) -> list[str]:
        return self.content_service.build_summary_lines(request)

    def _build_group_summary_sections(self, request: AnalysisExportRequest) -> list[GroupSummarySection]:
        return self.content_service.build_group_summary_sections(request)

    def _get_export_groups(self, request: AnalysisExportRequest):
        return self.content_service.get_export_groups(request)

    def _build_active_filter_lookup(self, request: AnalysisExportRequest) -> dict[str, list[str]]:
        return self.content_service.build_active_filter_lookup(request)

    def _build_subtitle(self, request: AnalysisExportRequest) -> str:
        return self.content_service.build_subtitle(request)

    def _build_report_title(self) -> str:
        return self.content_service.build_report_title()

    def _build_summary_heading(self, request: AnalysisExportRequest) -> str:
        return self.content_service.build_summary_heading(request)

    def _build_representative_heading(self) -> str:
        return self.content_service.build_representative_heading()

    def _build_representative_sections(self, request: AnalysisExportRequest) -> list[tuple[str, list[str]]]:
        return self.content_service.build_representative_sections(request)

    def _build_ngram_representative_sections(self, request: AnalysisExportRequest) -> list[tuple[str, list[str]]]:
        return self.content_service.build_ngram_representative_sections(request)

    def _build_filename_stem(self, request: AnalysisExportRequest) -> str:
        return self.content_service.build_filename_stem(request)

    def _filters_text(self, request: AnalysisExportRequest) -> str:
        return self.content_service.filters_text(request)

    def _row_count_text(self, request: AnalysisExportRequest) -> str:
        return self.content_service.row_count_text(request)

    def _decode_chart(self, chart: AnalysisExportChartModel) -> DecodedChartImage:
        return self.chart_image_service.decode_chart(chart)

    def _fit_image_to_bounds(self, *, width: int, height: int, max_width: float, max_height: float) -> tuple[float, float]:
        return self.chart_image_service.fit_image_to_bounds(
            width=width,
            height=height,
            max_width=max_width,
            max_height=max_height,
        )

    def _display_column_label(self, value: str) -> str:
        return self.content_service.display_column_label(value)

    def _strip_extension(self, filename: str) -> str:
        return self.content_service.strip_extension(filename)

    def _slugify(self, value: str) -> str:
        return self.content_service.slugify(value)

    def _escape(self, value: str) -> str:
        return self.content_service.escape(value)

    def _truncate_text(self, value: str, *, limit: int) -> str:
        return self.content_service.truncate_text(value, limit=limit)

    def _sanitize_chart_caption(self, value: str | None) -> str:
        return self.content_service.sanitize_chart_caption(value)

    def _normalize_export_chart_image(self, chart: DecodedChartImage) -> DecodedChartImage:
        return self.chart_image_service.normalize_export_chart_image(chart)

    def _trim_pptx_chart_image(self, chart: DecodedChartImage) -> DecodedChartImage:
        return self.chart_image_service.trim_pptx_chart_image(chart)
