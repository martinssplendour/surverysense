from __future__ import annotations

from base64 import b64encode
from io import BytesIO
from zipfile import ZipFile

from PIL import Image
from unittest import TestCase

from app.models.api import (
    AnalysisExportChartModel,
    AnalysisExportFilterModel,
    AnalysisExportRequest,
    AnalysisGroupModel,
    AnalysisRunResponse,
)
from app.services.report_export_service import AnalysisReportExportService


class AnalysisReportExportServiceTests(TestCase):
    def setUp(self) -> None:
        chart_buffer = BytesIO()
        Image.new("RGB", (320, 180), "#dce9df").save(chart_buffer, format="PNG")
        chart_data_url = "data:image/png;base64," + b64encode(chart_buffer.getvalue()).decode("ascii")

        self.request = AnalysisExportRequest(
            format="pdf",
            report_title="Requests for resources - AI Themes Report",
            source_filename="sample.csv",
            subtitle="AI Themes · question_text · 120 filtered rows · 100 usable responses",
            active_filters=[
                AnalysisExportFilterModel(
                    column_name="country",
                    display_name="Country",
                    values=["United Kingdom"],
                )
            ],
            charts=[
                AnalysisExportChartModel(
                    title="Response distribution",
                    caption="Distribution of grouped responses in the current filtered sample.",
                    image_data_url=chart_data_url,
                )
            ],
            analysis_result=AnalysisRunResponse(
                ok=True,
                result_id="abc123",
                model_key="bertopic",
                model_label="AI Themes",
                text_column_name="question_text",
                filtered_row_count=120,
                valid_document_count=100,
                skipped_document_count=20,
                translated_document_count=3,
                warnings=[],
                error=None,
                groups=[
                    AnalysisGroupModel(
                        group_id="1",
                        label="Requests for resources",
                        source_label=None,
                        translated=False,
                        ai_generated=False,
                        comment="Requests for resources appears in 40 responses.",
                        count=40,
                        share=0.4,
                        terms=["resources", "support", "materials"],
                        examples=[],
                        is_noise=False,
                    )
                ],
                ngram_buckets=[],
                scatter_points=[],
            ),
        )
        self.service = AnalysisReportExportService()

    def test_export_report_builds_pdf_document(self) -> None:
        self.request.format = "pdf"

        artifact = self.service.export_report(result_id="abc123", request=self.request)

        self.assertEqual(artifact.filename, "sample-ai-themes-report.pdf")
        self.assertEqual(artifact.media_type, "application/pdf")
        self.assertTrue(artifact.content.startswith(b"%PDF"))

    def test_export_report_builds_docx_document(self) -> None:
        self.request.format = "docx"

        artifact = self.service.export_report(result_id="abc123", request=self.request)

        self.assertEqual(
            artifact.media_type,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        with ZipFile(BytesIO(artifact.content)) as archive:
            self.assertIn("word/document.xml", archive.namelist())

    def test_export_report_builds_pptx_document(self) -> None:
        self.request.format = "pptx"

        artifact = self.service.export_report(result_id="abc123", request=self.request)

        self.assertEqual(
            artifact.media_type,
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
        with ZipFile(BytesIO(artifact.content)) as archive:
            self.assertIn("ppt/presentation.xml", archive.namelist())
