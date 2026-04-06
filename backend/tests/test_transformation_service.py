import unittest

import pandas as pd

from app.models.manifest import LayoutState, TransformationManifest
from app.services.cleaning_services import (
    DuplicateAnswerResolutionService,
    MetadataConsolidationService,
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


class DataTransformationServiceVerticalTests(unittest.TestCase):
    def setUp(self) -> None:
        text_normalizer = TextNormalizationService()
        self.service = DataTransformationService(
            text_normalizer=text_normalizer,
            null_scrubber=NullScrubbingService(),
            question_header_resolver=QuestionHeaderResolutionService(text_normalizer),
            verbatim_header_cleaner=VerbatimHeaderCleaningService(text_normalizer),
            vertical_record_filter=VerticalRecordFilterService(),
            duplicate_answer_resolver=DuplicateAnswerResolutionService(),
            metadata_consolidator=MetadataConsolidationService(),
            vertical_record_assembler=VerticalRecordAssemblyService(),
            row_filter=VerbatimRowFilterService(),
        )

    def test_vertical_manifest_assembles_one_row_per_record_by_indices(self) -> None:
        raw_df = pd.DataFrame(
            [
                [101, "UK", "Confidence", "Confidence: Guidance", "Draft answer", "unused", "unused"],
                [101, None, "Confidence", "Confidence: Guidance", "Final answer", "unused", "unused"],
                [101, "UK", "Support needed", "", "Shorter planning time", "unused", "unused"],
                [101, "UK", "Support needed", "", "Shorter planning time", "unused", "unused"],
                [202, "US", "Confidence", "Confidence: Guidance", "n/a", "unused", "unused"],
                [202, "US", "Support needed", "", "  ", "unused", "unused"],
                [303, "CA", "Confidence", "Confidence: Guidance", "Weekly snapshots", "unused", "unused"],
                [303, "CA", "Support needed", "", "Parent summaries", "unused", "unused"],
            ],
            columns=[
                "Respondent ID",
                "Region",
                "Main Question",
                "Full Question",
                "Answer",
                "Question Order",
                "Answer Number",
            ],
        )

        manifest = TransformationManifest(
            layout_state=LayoutState.VERTICAL,
            metadata_indices=[0, 1],
            verbatim_indices=[],
            vertical_assembly={
                "is_required": True,
                "record_key_indices": [0],
                "question_header_indices": [3, 2],
                "answer_col_idx": 4,
                "helper_indices": [5, 6],
                "duplicate_resolution": "last_non_null",
                "row_consolidation": "one_row_per_record",
            },
            null_equivalents=["", "n/a", "none", ".", "-", "<na>", "nan"],
            row_limit=5000,
            notes=[],
        )

        transformed = self.service.transform(raw_df, manifest)

        self.assertEqual(
            transformed.columns.tolist(),
            [
                "Respondent ID__idx_0",
                "Region__idx_1",
                "Confidence: Guidance",
                "Support needed",
            ],
        )
        self.assertEqual(len(transformed), 2)

        row_101 = transformed.loc[transformed["Respondent ID__idx_0"] == "101"].iloc[0]
        self.assertEqual(row_101["Region__idx_1"], "UK")
        self.assertEqual(row_101["Confidence: Guidance"], "Final answer")
        self.assertEqual(row_101["Support needed"], "Shorter planning time")

        row_303 = transformed.loc[transformed["Respondent ID__idx_0"] == "303"].iloc[0]
        self.assertEqual(row_303["Region__idx_1"], "CA")
        self.assertEqual(row_303["Confidence: Guidance"], "Weekly snapshots")
        self.assertEqual(row_303["Support needed"], "Parent summaries")

    def test_matrix_style_verbatim_headers_are_grouped_and_sorted(self) -> None:
        raw_df = pd.DataFrame(
            [
                [101, "UK", "Brand B: Building your confidence", "Answer B1"],
                [101, "UK", "Brand A: Building your confidence", "Answer A1"],
                [101, "UK", "Brand B: Saving you time", "Answer B2"],
                [101, "UK", "Brand A: Saving you time", "Answer A2"],
            ],
            columns=["Respondent ID", "Region", "Question", "Answer"],
        )

        manifest = TransformationManifest(
            layout_state=LayoutState.VERTICAL,
            metadata_indices=[0, 1],
            verbatim_indices=[],
            vertical_assembly={
                "is_required": True,
                "record_key_indices": [0],
                "question_header_indices": [2],
                "answer_col_idx": 3,
                "helper_indices": [],
                "duplicate_resolution": "last_non_null",
                "row_consolidation": "one_row_per_record",
            },
            null_equivalents=["", "n/a", "none", ".", "-", "<na>", "nan"],
            row_limit=5000,
            notes=[],
        )

        transformed = self.service.transform(raw_df, manifest)

        self.assertEqual(
            transformed.columns.tolist(),
            [
                "Respondent ID__idx_0",
                "Region__idx_1",
                "Building your confidence | Brand A",
                "Building your confidence | Brand B",
                "Saving you time | Brand A",
                "Saving you time | Brand B",
            ],
        )

class VerbatimQuestionSelectionServiceTests(unittest.TestCase):
    def test_selects_open_ended_columns_and_rejects_matrix_style_columns(self) -> None:
        service = VerbatimQuestionSelectionService()
        df = pd.DataFrame(
            [
                {
                    "response_id__idx_0": "1",
                    "country__idx_1": "UK",
                    "What more could Twinkl do to save you time?": "Provide weekly packs tailored to my class.",
                    "How likely are you to recommend Twinkl to a friend or colleague?": "10",
                    "Building your confidence | Brand A": "The same as Twinkl",
                    "We'd love to share some of the feedback you've given today to help others learn about Twinkl. Are you happy for us to use your comments in marketing?": "Yes, I give permission",
                    "Thanks, we'd love to know more about why you'd recommend Twinkl": "It saves me planning time every week.",
                },
                {
                    "response_id__idx_0": "2",
                    "country__idx_1": "US",
                    "What more could Twinkl do to save you time?": "Bundle the best matching resources together.",
                    "How likely are you to recommend Twinkl to a friend or colleague?": "8",
                    "Building your confidence | Brand A": "Better than Twinkl",
                    "We'd love to share some of the feedback you've given today to help others learn about Twinkl. Are you happy for us to use your comments in marketing?": "No, I do not give permission",
                    "Thanks, we'd love to know more about why you'd recommend Twinkl": "The resources are easy to find and adapt.",
                },
                {
                    "response_id__idx_0": "3",
                    "country__idx_1": "CA",
                    "What more could Twinkl do to save you time?": "Make curriculum-linked collections easier to browse.",
                    "How likely are you to recommend Twinkl to a friend or colleague?": "9",
                    "Building your confidence | Brand A": "Less well than Twinkl",
                    "We'd love to share some of the feedback you've given today to help others learn about Twinkl. Are you happy for us to use your comments in marketing?": "Yes, I give permission",
                    "Thanks, we'd love to know more about why you'd recommend Twinkl": "It gives me useful starting points for lessons.",
                },
            ]
        )

        metadata_columns = ["response_id__idx_0", "country__idx_1"]
        selected_columns = service.select_columns(df, metadata_columns=metadata_columns)

        self.assertEqual(
            selected_columns,
            [
                "What more could Twinkl do to save you time?",
                "Thanks, we'd love to know more about why you'd recommend Twinkl",
            ],
        )


if __name__ == "__main__":
    unittest.main()
