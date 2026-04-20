from __future__ import annotations

import unittest
from unittest.mock import patch

from app.application_setup import build_application_services
from app.core.auth import AuthenticatedUser
from app.core.settings import Settings
from app.main import create_app
from app.models.enums import AnalysisModelKey
from app.services.topic_analysis_services.contracts import (
    AnalysisExampleRecord,
    AnalysisGroupRecord,
    AnalysisRunResult,
)
from fastapi.testclient import TestClient

_SMALL_PNG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+nNcoAAAAASUVORK5CYII="
)


class _FakeTopicAnalysisService:
    def warm_up(self) -> None:
        return None

    def run(
        self,
        *,
        result_id: str,
        dataframe,
        model_key: AnalysisModelKey,
        text_column_name: str,
        available_verbatim_columns,
    ) -> AnalysisRunResult:
        texts = [
            str(value).strip()
            for value in dataframe[text_column_name].tolist()
            if str(value).strip()
        ]
        examples = [
            AnalysisExampleRecord(row_number=index + 1, text=text)
            for index, text in enumerate(texts[:3])
        ]
        return AnalysisRunResult(
            ok=True,
            result_id=result_id,
            model_key=model_key,
            model_label="Topic Clusters",
            text_column_name=text_column_name,
            filtered_row_count=int(len(dataframe)),
            valid_document_count=len(texts),
            skipped_document_count=max(0, int(len(dataframe)) - len(texts)),
            error=None,
            groups=[
                AnalysisGroupRecord(
                    group_id="support",
                    label="Need more support",
                    source_label=None,
                    translated=False,
                    ai_generated=False,
                    comment="Need more support appears in the current filtered responses.",
                    count=len(texts),
                    share=1.0 if texts else 0.0,
                    terms=["support", "resources", "guidance"],
                    examples=examples,
                    is_noise=False,
                )
            ],
            ngram_buckets=[],
            scatter_points=[],
        )


class IngestAnalysisExportIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(app_env="test", session_secret="test-session-secret")
        services = build_application_services(self.settings)
        services.topic_analysis_service = _FakeTopicAnalysisService()

        fake_user = AuthenticatedUser(email="tester@example.com", name="Test User")
        self.patchers = [
            patch("app.main.get_settings", return_value=self.settings),
            patch("app.main.build_application_services", return_value=services),
            patch("app.api._ingest_upload_routes.require_authenticated_user", return_value=fake_user),
            patch("app.api._ingest_analysis_routes.require_authenticated_user", return_value=fake_user),
            patch("app.api._ingest_result_routes.require_authenticated_user", return_value=fake_user),
        ]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

        self.client = TestClient(create_app())

    def test_upload_analysis_and_pdf_export_flow(self) -> None:
        csv_payload = (
            "country,team,comment\n"
            "UK,Maths,Need more classroom resources and clearer lesson guidance.\n"
            "US,Science,More printable materials would help teachers feel prepared.\n"
            "ZA,English,Extra examples and adaptable worksheets would save time.\n"
            "AU,Humanities,Better support for planning would build confidence.\n"
        )

        upload_response = self.client.post(
            "/upload-ingest",
            files={"file": ("sample.csv", csv_payload, "text/csv")},
            data={"diagnostic_mode": "rule_based"},
        )

        self.assertEqual(upload_response.status_code, 200)
        upload_payload = upload_response.json()
        self.assertEqual(upload_payload["filename"], "sample.csv")
        self.assertGreater(upload_payload["analysis_row_count"], 0)
        self.assertEqual(len(upload_payload["analysis_verbatim_column_names"]), 1)

        result_id = upload_payload["result_id"]
        text_column_name = upload_payload["analysis_verbatim_column_names"][0]

        analysis_response = self.client.post(
            f"/run-analysis/{result_id}",
            json={
                "model_key": "bertopic",
                "text_column_name": text_column_name,
                "filters": {},
            },
        )

        self.assertEqual(analysis_response.status_code, 200)
        analysis_payload = analysis_response.json()
        self.assertTrue(analysis_payload["ok"])
        self.assertEqual(analysis_payload["model_key"], "bertopic")
        self.assertEqual(analysis_payload["text_column_name"], text_column_name)
        self.assertEqual(analysis_payload["groups"][0]["label"], "Need more support")

        export_response = self.client.post(
            f"/analysis-export/{result_id}",
            json={
                "format": "pdf",
                "report_title": "Support themes report",
                "source_filename": "sample.csv",
                "subtitle": f"Topic Clusters | {text_column_name} | {analysis_payload['filtered_row_count']} rows",
                "active_filters": [],
                "charts": [
                    {
                        "title": "Response distribution",
                        "caption": "Grouped response distribution for the filtered sample.",
                        "image_data_url": _SMALL_PNG_DATA_URL,
                    }
                ],
                "analysis_result": analysis_payload,
            },
        )

        self.assertEqual(export_response.status_code, 200)
        self.assertEqual(export_response.headers["content-type"], "application/pdf")
        self.assertIn(".pdf", export_response.headers["content-disposition"])
        self.assertTrue(export_response.content.startswith(b"%PDF"))

    def test_upload_can_export_clean_data_and_verbatim_only_csvs(self) -> None:
        csv_payload = (
            "country,team,comment,score\n"
            "UK,Maths,Need more classroom resources,9\n"
            "US,Science,More printable materials would help,8\n"
            "ZA,English,Extra examples would save time,7\n"
        )

        upload_response = self.client.post(
            "/upload-ingest",
            files={"file": ("sample.csv", csv_payload, "text/csv")},
            data={"diagnostic_mode": "rule_based"},
        )

        self.assertEqual(upload_response.status_code, 200)
        result_id = upload_response.json()["result_id"]

        clean_export = self.client.get(
            f"/result-export/{result_id}",
            params={
                "scope": "clean_data",
                "source_filename": "sample.csv",
            },
        )
        self.assertEqual(clean_export.status_code, 200)
        self.assertEqual(clean_export.headers["content-type"], "text/csv; charset=utf-8")
        self.assertIn("sample_clean_data.csv", clean_export.headers["content-disposition"])
        clean_text = clean_export.content.decode("utf-8-sig")
        self.assertIn("country__idx_0", clean_text)
        self.assertIn("comment", clean_text)
        self.assertIn("score__idx_3", clean_text)

        verbatim_export = self.client.get(
            f"/result-export/{result_id}",
            params={
                "scope": "verbatim_only",
                "source_filename": "sample.csv",
            },
        )
        self.assertEqual(verbatim_export.status_code, 200)
        self.assertEqual(verbatim_export.headers["content-type"], "text/csv; charset=utf-8")
        self.assertIn("sample_verbatim_columns.csv", verbatim_export.headers["content-disposition"])
        verbatim_text = verbatim_export.content.decode("utf-8-sig")
        self.assertIn("comment", verbatim_text)
        self.assertNotIn("country__idx_0", verbatim_text)
        self.assertNotIn("score__idx_3", verbatim_text)
