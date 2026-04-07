import unittest

import pandas as pd

from app.services.architect_service import ManifestArchitectConfig, ManifestArchitectService
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


if __name__ == "__main__":
    unittest.main()
