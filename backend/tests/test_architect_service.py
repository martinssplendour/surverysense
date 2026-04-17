import unittest
import json
from unittest.mock import patch

import pandas as pd

from app.core.exceptions import ManifestBuildError
from app.services.architect_service import ManifestArchitectConfig, ManifestArchitectService
from app.services.architect_service import DiagnosticMode
from app.services.cleaning_services import (
    DuplicateAnswerResolutionService,
    MetadataConsolidationService,
    MultipartVerbatimConsolidationService,
    NullScrubbingService,
    QuestionHeaderResolutionService,
    TextNormalizationService,
    VerbatimHeaderCleaningService,
    VerbatimQuestionSelectionService,
    VerbatimRowFilterService,
    VerticalRecordAssemblyService,
    VerticalRecordFilterService,
)
from app.services.transformation_service import DataTransformationService
from app.models.manifest import LayoutState, TransformationManifest


class ManifestArchitectServiceHeuristicTests(unittest.TestCase):
    def setUp(self) -> None:
        self.architect_service = ManifestArchitectService(
            ManifestArchitectConfig(
                gemini_api_key="",
                gemini_model="gemini-2.5-flash",
                gemini_temperature=0.1,
                gemini_timeout_seconds=60,
                row_limit=5000,
            )
        )

        text_normalizer = TextNormalizationService()
        self.transformation_service = DataTransformationService(
            text_normalizer=text_normalizer,
            null_scrubber=NullScrubbingService(),
            question_header_resolver=QuestionHeaderResolutionService(text_normalizer),
            verbatim_header_cleaner=VerbatimHeaderCleaningService(text_normalizer),
            multipart_verbatim_consolidator=MultipartVerbatimConsolidationService(text_normalizer),
            vertical_record_filter=VerticalRecordFilterService(),
            duplicate_answer_resolver=DuplicateAnswerResolutionService(),
            metadata_consolidator=MetadataConsolidationService(),
            vertical_record_assembler=VerticalRecordAssemblyService(),
            row_filter=VerbatimRowFilterService(),
        )
        self.verbatim_selector = VerbatimQuestionSelectionService()

    def test_vertical_manifest_prefers_question_titles_over_survey_title(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "response_id": "resp-001",
                    "survey_title": "Our promise to you",
                    "question_order_number": "25",
                    "main_title": "What more could Twinkl do to save you time?",
                    "full_title": "",
                    "sub_title": "",
                    "answer_value": "More ready-made packs",
                    "answer_number": "1",
                    "user_id": "1001",
                    "country": "United Kingdom",
                },
                {
                    "response_id": "resp-001",
                    "survey_title": "Our promise to you",
                    "question_order_number": "366",
                    "main_title": "Thanks, we'd love to know more about why you'd recommend Twinkl",
                    "full_title": "",
                    "sub_title": "",
                    "answer_value": "It saves me planning time.",
                    "answer_number": "1",
                    "user_id": "1001",
                    "country": "United Kingdom",
                },
                {
                    "response_id": "resp-001",
                    "survey_title": "Our promise to you",
                    "question_order_number": "401",
                    "main_title": "Being effective and created by experts",
                    "full_title": "ABCmouse: Being effective and created by experts",
                    "sub_title": "",
                    "answer_value": "Better than Twinkl",
                    "answer_number": "1",
                    "user_id": "1001",
                    "country": "United Kingdom",
                },
                {
                    "response_id": "resp-002",
                    "survey_title": "Our promise to you",
                    "question_order_number": "25",
                    "main_title": "What more could Twinkl do to save you time?",
                    "full_title": "",
                    "sub_title": "",
                    "answer_value": "Bundle the best resources together.",
                    "answer_number": "1",
                    "user_id": "1002",
                    "country": "United States",
                },
                {
                    "response_id": "resp-002",
                    "survey_title": "Our promise to you",
                    "question_order_number": "366",
                    "main_title": "Thanks, we'd love to know more about why you'd recommend Twinkl",
                    "full_title": "",
                    "sub_title": "",
                    "answer_value": "The resources are easy to adapt.",
                    "answer_number": "1",
                    "user_id": "1002",
                    "country": "United States",
                },
                {
                    "response_id": "resp-002",
                    "survey_title": "Our promise to you",
                    "question_order_number": "401",
                    "main_title": "Being effective and created by experts",
                    "full_title": "ABCmouse: Being effective and created by experts",
                    "sub_title": "",
                    "answer_value": "The same as Twinkl",
                    "answer_number": "1",
                    "user_id": "1002",
                    "country": "United States",
                },
                {
                    "response_id": "resp-003",
                    "survey_title": "Our promise to you",
                    "question_order_number": "25",
                    "main_title": "What more could Twinkl do to save you time?",
                    "full_title": "",
                    "sub_title": "",
                    "answer_value": "Create clearer curriculum pathways.",
                    "answer_number": "1",
                    "user_id": "1003",
                    "country": "Canada",
                },
                {
                    "response_id": "resp-003",
                    "survey_title": "Our promise to you",
                    "question_order_number": "366",
                    "main_title": "Thanks, we'd love to know more about why you'd recommend Twinkl",
                    "full_title": "",
                    "sub_title": "",
                    "answer_value": "It gives me strong lesson starting points.",
                    "answer_number": "1",
                    "user_id": "1003",
                    "country": "Canada",
                },
                {
                    "response_id": "resp-003",
                    "survey_title": "Our promise to you",
                    "question_order_number": "401",
                    "main_title": "Being effective and created by experts",
                    "full_title": "ABCmouse: Being effective and created by experts",
                    "sub_title": "",
                    "answer_value": "Less well than Twinkl",
                    "answer_number": "1",
                    "user_id": "1003",
                    "country": "Canada",
                },
            ]
        )

        manifest = self.architect_service.get_transformation_manifest(
            df,
            {index: str(column) for index, column in enumerate(df.columns)},
        )

        self.assertEqual(manifest.layout_state.value, "VERTICAL")
        self.assertEqual(manifest.vertical_assembly.record_key_indices, [0])
        self.assertEqual(manifest.vertical_assembly.answer_col_idx, 6)
        self.assertEqual(manifest.vertical_assembly.question_header_indices[:2], [4, 3])
        self.assertNotIn(1, manifest.vertical_assembly.question_header_indices)

        transformed = self.transformation_service.transform(df, manifest)
        metadata_columns = [column for column in transformed.columns if "__idx_" in column]
        selected_columns = self.verbatim_selector.select_columns(
            transformed,
            metadata_columns=metadata_columns,
        )

        self.assertIn("What more could Twinkl do to save you time?", transformed.columns.tolist())
        self.assertIn(
            "Thanks, we'd love to know more about why you'd recommend Twinkl",
            transformed.columns.tolist(),
        )
        self.assertIn("What more could Twinkl do to save you time?", selected_columns)
        self.assertIn(
            "Thanks, we'd love to know more about why you'd recommend Twinkl",
            selected_columns,
        )
        self.assertNotIn("Our promise to you", transformed.columns.tolist())

    def test_vertical_manifest_does_not_treat_uuid_response_ids_as_answers(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "response_id": "019be56e-769c-0e63-fc8e-dceb6bb65eab",
                    "survey_month": "2026-02",
                    "main_title": "How can we better help you see and track the progress your child is making with their learning?",
                    "full_title": "",
                    "sub_title": "",
                    "answer_value": "Show progress in a simpler dashboard with clearer milestones.",
                    "answer_number": "1",
                    "user_id": "1001",
                },
                {
                    "response_id": "019be56e-769c-0e63-fc8e-dceb6bb65eab",
                    "survey_month": "2026-02",
                    "main_title": "How can we help you feel more certain that the activities you use at home are effective and created by experts?",
                    "full_title": "",
                    "sub_title": "",
                    "answer_value": "Explain the learning goals more clearly for parents.",
                    "answer_number": "2",
                    "user_id": "1001",
                },
                {
                    "response_id": "019bf585-6242-f925-950a-8a940b2d4198",
                    "survey_month": "2026-02",
                    "main_title": "How can Twinkl better equip you with the skills and confidence you need to support your child's learning journey?",
                    "full_title": "",
                    "sub_title": "",
                    "answer_value": "Add more short guides that show how to use each activity.",
                    "answer_number": "1",
                    "user_id": "1002",
                },
                {
                    "response_id": "019bf585-6242-f925-950a-8a940b2d4198",
                    "survey_month": "2026-02",
                    "main_title": "How can we better help you celebrate the hard work and success you and your child achieve together?",
                    "full_title": "",
                    "sub_title": "",
                    "answer_value": "Include printable certificates for milestones at home.",
                    "answer_number": "2",
                    "user_id": "1002",
                },
            ]
        )

        manifest = self.architect_service.get_transformation_manifest(
            df,
            {index: str(column) for index, column in enumerate(df.columns)},
        )

        self.assertEqual(manifest.layout_state.value, "VERTICAL")
        self.assertEqual(manifest.vertical_assembly.record_key_indices, [0])
        self.assertEqual(manifest.vertical_assembly.answer_col_idx, 5)

    def test_ai_mode_requires_gemini_key(self) -> None:
        df = pd.DataFrame(
            [
                {"response_id": "resp-001", "main_title": "Q1", "answer_value": "A1"},
                {"response_id": "resp-001", "main_title": "Q2", "answer_value": "A2"},
            ]
        )

        with self.assertRaises(ManifestBuildError):
            self.architect_service.get_transformation_manifest(
                df,
                {index: str(column) for index, column in enumerate(df.columns)},
                diagnostic_mode=DiagnosticMode.AI,
            )

    def test_ai_mode_uses_gemini_path_when_configured(self) -> None:
        service = ManifestArchitectService(
            ManifestArchitectConfig(
                gemini_api_key="test-key",
                gemini_model="gemini-2.5-flash",
                gemini_temperature=0.1,
                gemini_timeout_seconds=60,
                row_limit=5000,
            )
        )
        df = pd.DataFrame([{"col_a": "value"}])
        manifest = TransformationManifest(
            diagnostic_source="gemini",
            layout_state=LayoutState.WIDE,
            metadata_indices=[],
            verbatim_indices=[0],
            vertical_assembly={"is_required": False},
            null_equivalents=["", "n/a", "none"],
            row_limit=5000,
            notes=["AI manifest"],
        )

        with patch.object(service, "_build_manifest_with_gemini", return_value=manifest) as mocked_builder:
            result = service.get_transformation_manifest(
                df,
                {0: "col_a"},
                diagnostic_mode=DiagnosticMode.AI,
            )

        mocked_builder.assert_called_once()
        self.assertEqual(result.diagnostic_source, "gemini")

    def test_build_manifest_with_gemini_uses_api_key_header(self) -> None:
        service = ManifestArchitectService(
            ManifestArchitectConfig(
                gemini_api_key="test-key",
                gemini_model="gemini-2.5-flash",
                gemini_temperature=0.1,
                gemini_timeout_seconds=60,
                row_limit=5000,
            )
        )
        df = pd.DataFrame([{"col_a": "value"}])

        class _FakeHttpResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps(
                    {
                        "candidates": [
                            {
                                "content": {
                                    "parts": [
                                        {
                                            "text": json.dumps(
                                                {
                                                    "diagnostic_source": "gemini",
                                                    "layout_state": "WIDE",
                                                    "metadata_indices": [],
                                                    "verbatim_indices": [0],
                                                    "vertical_assembly": {"is_required": False},
                                                    "null_equivalents": ["", "n/a", "none"],
                                                    "row_limit": 5000,
                                                    "notes": ["AI manifest"],
                                                }
                                            )
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                ).encode("utf-8")

        def _fake_urlopen(request, timeout):
            self.assertEqual(timeout, 60)
            self.assertNotIn("?key=", request.full_url)
            headers = {key.casefold(): value for key, value in request.header_items()}
            self.assertEqual(headers.get("x-goog-api-key"), "test-key")
            return _FakeHttpResponse()

        with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            manifest = service._build_manifest_with_gemini(df, {0: "col_a"})

        self.assertEqual(manifest.diagnostic_source, "gemini")


if __name__ == "__main__":
    unittest.main()
