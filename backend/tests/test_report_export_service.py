from __future__ import annotations

from base64 import b64encode
from io import BytesIO
from types import SimpleNamespace
from unittest import TestCase
from zipfile import ZipFile

from app.models.api import (
    AnalysisExampleModel,
    AnalysisExportChartModel,
    AnalysisExportFilterModel,
    AnalysisExportRequest,
    AnalysisGroupModel,
    AnalysisNgramBucketModel,
    AnalysisNgramItemModel,
    AnalysisRunResponse,
)
from app.models.enums import AnalysisModelKey
from app.services.report_export_service import AnalysisReportExportService, DecodedChartImage
from app.services.topic_analysis_services.contracts import (
    AnalysisExampleRecord,
    AnalysisGroupRecord,
    AnalysisRunResult,
)
from PIL import Image


class AnalysisReportExportServiceTests(TestCase):
    def setUp(self) -> None:
        chart_buffer = BytesIO()
        Image.new("RGB", (320, 180), "#dce9df").save(chart_buffer, format="PNG")
        chart_data_url = "data:image/png;base64," + b64encode(chart_buffer.getvalue()).decode("ascii")

        self.request = AnalysisExportRequest(
            format="pdf",
            report_title="Requests for resources - Topic Clusters Report",
            source_filename="sample.csv",
            subtitle="Topic Clusters | question_text | 120 filtered rows | 100 usable responses",
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

    def test_export_report_builds_docx_document_with_expected_sections(self) -> None:
        self.request.format = "docx"

        artifact = self.service.export_report(result_id="abc123", request=self.request)

        self.assertEqual(
            artifact.media_type,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        with ZipFile(BytesIO(artifact.content)) as archive:
            self.assertIn("word/document.xml", archive.namelist())
            document_xml = archive.read("word/document.xml").decode("utf-8")
            self.assertIn("question_text | Country: United Kingdom | 120 rows", document_xml)
            self.assertIn("Topic summaries", document_xml)
            self.assertIn("Representative documents (topics and top 3 responses)", document_xml)
            self.assertIn("Requests for resources", document_xml)
            self.assertIn("Give us clearer guidance and more classroom resources.", document_xml)

    def test_export_report_builds_pptx_document_with_expected_sections(self) -> None:
        self.request.format = "pptx"

        artifact = self.service.export_report(result_id="abc123", request=self.request)

        self.assertEqual(
            artifact.media_type,
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
        with ZipFile(BytesIO(artifact.content)) as archive:
            self.assertIn("ppt/presentation.xml", archive.namelist())
            slide_xml = "\n".join(
                archive.read(name).decode("utf-8")
                for name in archive.namelist()
                if name.startswith("ppt/slides/slide") and name.endswith(".xml")
            )
            self.assertIn("question_text | Country: United Kingdom | 120 rows", slide_xml)
            self.assertIn("Topic summaries", slide_xml)
            self.assertIn("Representative documents (topics and top 3 responses)", slide_xml)
            self.assertIn("Requests for resources", slide_xml)
            self.assertIn("Give us clearer guidance and more classroom resources.", slide_xml)

    def test_export_report_builds_ngram_representative_sections_when_store_available(self) -> None:
        class FakeResultStoreService:
            def get_fast_filtered_result(self, result_id, *, model_key, text_column_name, filters):
                return None

            def get_analysis_ngram_page(self, result_id, *, ngram_size, term, offset, limit):
                documents_by_term = {
                    "resources": [
                        {"row_number": 4, "text": "Give us clearer guidance and more classroom resources."},
                        {"row_number": 11, "text": "More practical support materials would build confidence."},
                        {"row_number": 18, "text": "Access to better planning resources would help a lot."},
                    ],
                    "lesson plans": [
                        {"row_number": 21, "text": "Lesson plans should be simpler and quicker to adapt."},
                        {"row_number": 27, "text": "More lesson plans for mixed ability groups would help."},
                        {"row_number": 33, "text": "Detailed lesson plans would improve confidence."},
                    ],
                    "materials": [
                        {"row_number": 42, "text": "More printable materials would save time."},
                        {"row_number": 48, "text": "Updated materials are needed for SEND learners."},
                        {"row_number": 54, "text": "High quality materials build teacher confidence."},
                    ],
                }
                return SimpleNamespace(documents=documents_by_term.get(term, [])[:limit])

        request = AnalysisExportRequest(
            format="pptx",
            report_title="Repeated words and phrases report",
            source_filename="sample.csv",
            subtitle="Repeated words and phrases | question_text | 120 rows",
            active_filters=[
                AnalysisExportFilterModel(
                    column_name="country",
                    display_name="Country",
                    values=["United Kingdom"],
                )
            ],
            charts=self.request.charts,
            analysis_result=AnalysisRunResponse(
                ok=True,
                result_id="abc123",
                model_key="ngrams",
                model_label="Repeated words and phrases",
                text_column_name="question_text",
                filtered_row_count=120,
                valid_document_count=100,
                skipped_document_count=20,
                translated_document_count=0,
                warnings=[],
                error=None,
                groups=[],
                ngram_buckets=[
                    AnalysisNgramBucketModel(
                        label="Single Words",
                        ngram_size=1,
                        items=[AnalysisNgramItemModel(term="resources", count=386, document_count=386)],
                    ),
                    AnalysisNgramBucketModel(
                        label="Two-Word Phrases",
                        ngram_size=2,
                        items=[AnalysisNgramItemModel(term="lesson plans", count=25, document_count=25)],
                    ),
                    AnalysisNgramBucketModel(
                        label="Three-Word Phrases",
                        ngram_size=3,
                        items=[AnalysisNgramItemModel(term="materials", count=10, document_count=10)],
                    ),
                ],
                scatter_points=[],
            ),
        )
        service = AnalysisReportExportService(result_store_service=FakeResultStoreService())

        artifact = service.export_report(result_id="abc123", request=request)

        with ZipFile(BytesIO(artifact.content)) as archive:
            slide_xml = "\n".join(
                archive.read(name).decode("utf-8")
                for name in archive.namelist()
                if name.startswith("ppt/slides/slide") and name.endswith(".xml")
            )
            self.assertIn("Representative documents (topics and top 3 responses)", slide_xml)
            self.assertIn("Single Words: resources", slide_xml)
            self.assertIn("Two-Word Phrases: lesson plans", slide_xml)
            self.assertIn("Three-Word Phrases: materials", slide_xml)
            self.assertIn("Give us clearer guidance and more classroom resources.", slide_xml)

    def test_export_report_hydrates_group_examples_from_store_when_request_groups_are_thin(self) -> None:
        class FakeResultStoreService:
            def get_fast_filtered_result(self, result_id, *, model_key, text_column_name, filters):
                return AnalysisRunResult(
                    ok=True,
                    result_id=result_id,
                    model_key=AnalysisModelKey.BERTOPIC,
                    model_label="Topic Clusters",
                    text_column_name=text_column_name,
                    filtered_row_count=120,
                    valid_document_count=100,
                    groups=[
                        AnalysisGroupRecord(
                            group_id="1",
                            label="Requests for resources",
                            count=40,
                            share=0.4,
                            terms=["resources", "support", "materials"],
                            examples=[
                                AnalysisExampleRecord(row_number=4, text="Give us clearer guidance and more classroom resources."),
                                AnalysisExampleRecord(row_number=11, text="More practical support materials would build confidence."),
                                AnalysisExampleRecord(row_number=18, text="Access to better planning resources would help a lot."),
                            ],
                        )
                    ],
                )

        request = self.request.model_copy(deep=True)
        request.format = "pptx"
        request.analysis_result.groups = [
            AnalysisGroupModel(
                group_id="1",
                label="Requests for resources",
                source_label=None,
                translated=False,
                ai_generated=False,
                comment="",
                count=40,
                share=0.4,
                terms=["resources", "support", "materials"],
                examples=[],
                is_noise=False,
            )
        ]
        service = AnalysisReportExportService(result_store_service=FakeResultStoreService())

        artifact = service.export_report(result_id="abc123", request=request)

        with ZipFile(BytesIO(artifact.content)) as archive:
            slide_xml = "\n".join(
                archive.read(name).decode("utf-8")
                for name in archive.namelist()
                if name.startswith("ppt/slides/slide") and name.endswith(".xml")
            )
            self.assertIn("Representative documents (topics and top 3 responses)", slide_xml)
            self.assertIn("Requests for resources", slide_xml)
            self.assertIn("Give us clearer guidance and more classroom resources.", slide_xml)

    def test_build_subtitle_uses_clean_single_line_metadata(self) -> None:
        self.assertEqual(
            self.service._build_subtitle(self.request),
            "question_text | Country: United Kingdom | 120 rows",
        )

    def test_build_summary_heading_uses_topic_wording_for_group_exports(self) -> None:
        self.assertEqual(self.service._build_summary_heading(self.request), "Topic summaries")

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
