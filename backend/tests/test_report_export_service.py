from __future__ import annotations

from base64 import b64encode
from io import BytesIO
from zipfile import ZipFile

from PIL import Image
from unittest import TestCase

from app.models.api import (
    AnalysisExampleModel,
    AnalysisExportChartModel,
    AnalysisExportFilterModel,
    AnalysisExportRequest,
    AnalysisGroupModel,
    AnalysisRunResponse,
)
from app.services.report_export_service import AnalysisReportExportService, DecodedChartImage


class AnalysisReportExportServiceTests(TestCase):
    def setUp(self) -> None:
        chart_buffer = BytesIO()
        Image.new("RGB", (320, 180), "#dce9df").save(chart_buffer, format="PNG")
        chart_data_url = "data:image/png;base64," + b64encode(chart_buffer.getvalue()).decode("ascii")

        self.request = AnalysisExportRequest(
            format="pdf",
            report_title="Requests for resources - Topic Clusters Report",
            source_filename="sample.csv",
            subtitle="Topic Clusters · question_text · 120 filtered rows · 100 usable responses",
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
                model_label="Topic Clusters",
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
                        examples=[
                            AnalysisExampleModel(row_number=4, text="Give us clearer guidance and more classroom resources."),
                            AnalysisExampleModel(row_number=11, text="More practical support materials would build confidence."),
                            AnalysisExampleModel(row_number=18, text="Access to better planning resources would help a lot."),
                        ],
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

        self.assertEqual(artifact.filename, "sample-topic-clusters-report.pdf")
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
            document_xml = archive.read("word/document.xml").decode("utf-8")
            self.assertIn("question_text", document_xml)
            self.assertIn("Country: United Kingdom", document_xml)
            self.assertIn("120 rows", document_xml)
            self.assertIn("question_text · Country: United Kingdom · 120 rows", document_xml)

    def test_export_report_builds_pptx_document(self) -> None:
        self.request.format = "pptx"

        artifact = self.service.export_report(result_id="abc123", request=self.request)

        self.assertEqual(
            artifact.media_type,
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
        with ZipFile(BytesIO(artifact.content)) as archive:
            self.assertIn("ppt/presentation.xml", archive.namelist())
            slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")
            self.assertIn("Country: United Kingdom", slide_xml)
            self.assertIn("120 rows", slide_xml)

    def test_trim_pptx_chart_image_removes_uniform_border(self) -> None:
        buffer = BytesIO()
        image = Image.new("RGB", (220, 140), "#f7f2ea")
        for x in range(60, 180):
            for y in range(40, 110):
                image.putpixel((x, y), (41, 75, 59))
        image.save(buffer, format="PNG")

        trimmed = self.service._trim_pptx_chart_image(
            DecodedChartImage(
                title="Single Words",
                caption="",
                image_bytes=buffer.getvalue(),
                width=220,
                height=140,
            )
        )

        self.assertLess(trimmed.width, 220)
        self.assertLess(trimmed.height, 140)
