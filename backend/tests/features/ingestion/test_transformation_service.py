import unittest

import pandas as pd
from app.models.manifest import LayoutState, TransformationManifest
from app.features.ingestion.cleaning_services import (
    AnalysisReadyDatasetService,
    DuplicateAnswerResolutionService,
    MetadataColumnSelectionService,
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
from app.features.ingestion.transformation_service import DataTransformationService


class RecordingTextNormalizationService(TextNormalizationService):
    def __init__(self) -> None:
        super().__init__()
        self.cleaned_column_calls: list[list[str]] = []

    def clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        self.cleaned_column_calls.append(df.columns.tolist())
        return super().clean_dataframe(df)


class DataTransformationServiceVerticalTests(unittest.TestCase):
    def setUp(self) -> None:
        text_normalizer = TextNormalizationService()
        self.service = DataTransformationService(
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

    def test_wide_multipart_word_columns_are_consolidated_into_one_question(self) -> None:
        raw_df = pd.DataFrame(
            [
                [
                    "resp-001",
                    "Slow",
                    "Clunky",
                    "Confusing",
                    "UK",
                ],
                [
                    "resp-002",
                    "Helpful",
                    "Creative",
                    None,
                    "US",
                ],
            ],
            columns=[
                "Response ID",
                "24.1: What three words best describe the frustrations of Twinkl?: Word 1",
                "24.2: What three words best describe the frustrations of Twinkl?: Word 2",
                "24.3: What three words best describe the frustrations of Twinkl?: Word 3",
                "Country",
            ],
        )

        manifest = TransformationManifest(
            layout_state=LayoutState.WIDE,
            metadata_indices=[0, 4],
            verbatim_indices=[1, 2, 3],
            vertical_assembly={"is_required": False},
            null_equivalents=["", "n/a", "none", ".", "-", "<na>", "nan"],
            row_limit=5000,
            notes=[],
        )

        transformed = self.service.transform(raw_df, manifest)

        self.assertEqual(
            transformed.columns.tolist(),
            [
                "Response ID__idx_0",
                "Country__idx_4",
                "What three words best describe the frustrations of Twinkl?",
            ],
        )
        self.assertEqual(
            transformed["What three words best describe the frustrations of Twinkl?"].tolist(),
            [
                "Slow, Clunky, Confusing",
                "Helpful, Creative",
            ],
        )

    def test_first_pass_scopes_wide_cleaning_to_manifest_columns(self) -> None:
        text_normalizer = RecordingTextNormalizationService()
        service = DataTransformationService(
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
        raw_df = pd.DataFrame(
            [
                ["resp-001", "unused a", "Helpful response", "unused b", "UK"],
            ],
            columns=["Response ID", "Unused A", "Verbatim", "Unused B", "Country"],
        )
        manifest = TransformationManifest(
            layout_state=LayoutState.WIDE,
            metadata_indices=[0, 4],
            verbatim_indices=[2],
            vertical_assembly={"is_required": False},
            null_equivalents=["", "n/a", "none", ".", "-", "<na>", "nan"],
            row_limit=5000,
            notes=[],
        )

        service.transform(raw_df, manifest)

        self.assertEqual(
            text_normalizer.cleaned_column_calls[0],
            ["Response ID", "Verbatim", "Country"],
        )

    def test_first_pass_scopes_vertical_cleaning_to_manifest_columns(self) -> None:
        text_normalizer = RecordingTextNormalizationService()
        service = DataTransformationService(
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
        raw_df = pd.DataFrame(
            [
                ["101", "unused", "Confidence", "Confidence: Guidance", "Answer", "1", "UK", "unused extra"],
            ],
            columns=[
                "Respondent ID",
                "Unused",
                "Main Question",
                "Full Question",
                "Answer",
                "Question Order",
                "Region",
                "Unused Extra",
            ],
        )
        manifest = TransformationManifest(
            layout_state=LayoutState.VERTICAL,
            metadata_indices=[6],
            verbatim_indices=[],
            vertical_assembly={
                "is_required": True,
                "record_key_indices": [0],
                "question_header_indices": [3, 2],
                "answer_col_idx": 4,
                "helper_indices": [5],
                "duplicate_resolution": "last_non_null",
                "row_consolidation": "one_row_per_record",
            },
            null_equivalents=["", "n/a", "none", ".", "-", "<na>", "nan"],
            row_limit=5000,
            notes=[],
        )

        service.transform(raw_df, manifest)

        self.assertEqual(
            text_normalizer.cleaned_column_calls[0],
            [
                "Respondent ID",
                "Main Question",
                "Full Question",
                "Answer",
                "Question Order",
                "Region",
            ],
        )


class QuestionHeaderResolutionServiceTests(unittest.TestCase):
    def test_resolve_skips_nan_like_values_and_uses_fallback_titles(self) -> None:
        text_normalizer = TextNormalizationService()
        service = QuestionHeaderResolutionService(text_normalizer)
        raw_df = pd.DataFrame(
            [
                {
                    "full_title": float("nan"),
                    "main_title": "What more could Twinkl do to save you time?",
                    "sub_title": None,
                },
                {
                    "full_title": "",
                    "main_title": "Thanks, please tell us more about your score",
                    "sub_title": None,
                },
                {
                    "full_title": None,
                    "main_title": None,
                    "sub_title": "Fallback subtitle",
                },
            ]
        )

        resolved = service.resolve(raw_df, [0, 1, 2])

        self.assertEqual(
            resolved.tolist(),
            [
                "What more could Twinkl do to save you time?",
                "Thanks, please tell us more about your score",
                "Fallback subtitle",
            ],
        )


class VerbatimQuestionSelectionServiceTests(unittest.TestCase):
    def test_selects_varied_text_columns_and_rejects_numeric_and_fixed_response_text(self) -> None:
        service = VerbatimQuestionSelectionService()
        rows = []
        role_values = ["Teacher", "Senior Leader", "Headteacher", "Teacher"]
        matrix_values = ["Yes, Twinkl is better", "No", "Yes, Twinkl is better", "Yes, Twinkl is better"]
        permission_values = ["Yes, I give permission", "No, I do not give permission"]
        for idx in range(24):
            rows.append(
                {
                    "response_id__idx_0": str(idx + 1),
                    "country__idx_1": ["UK", "US", "CA"][idx % 3],
                    "What more could Twinkl do to save you time?": f"Open answer about saving time number {idx}.",
                    "How likely are you to recommend Twinkl to a friend or colleague?": f"{(idx % 11)}",
                    "Which of the following best describes your role?": role_values[idx % len(role_values)],
                    "Building your confidence | Brand A": matrix_values[idx % len(matrix_values)],
                    "We'd love to share some of the feedback you've given today to help others learn about Twinkl. Are you happy for us to use your comments in marketing?": permission_values[idx % len(permission_values)],
                    "Thanks, we'd love to know more about why you'd recommend Twinkl": f"Recommendation reason number {idx} with different wording.",
                }
            )
        df = pd.DataFrame(rows)

        metadata_columns = ["response_id__idx_0", "country__idx_1"]
        selected_columns = service.select_columns(df, metadata_columns=metadata_columns)

        self.assertEqual(
            selected_columns,
            [
                "What more could Twinkl do to save you time?",
                "Thanks, we'd love to know more about why you'd recommend Twinkl",
            ],
        )

    def test_can_select_long_text_column_without_open_ended_trigger_words(self) -> None:
        service = VerbatimQuestionSelectionService()
        df = pd.DataFrame(
            [
                {
                    "response_id__idx_0": "1",
                    "Classroom resource experience reflections this term": "The resources were easy to adapt and saved me planning time.",
                },
                {
                    "response_id__idx_0": "2",
                    "Classroom resource experience reflections this term": "I found the materials strong overall but wanted clearer progression between lessons.",
                },
                {
                    "response_id__idx_0": "3",
                    "Classroom resource experience reflections this term": "The content quality was good and the worksheets helped with quick preparation.",
                },
            ]
        )

        selected_columns = service.select_columns(df, metadata_columns=["response_id__idx_0"])

        self.assertEqual(
            selected_columns,
            ["Classroom resource experience reflections this term"],
        )

    def test_rejects_columns_with_numeric_only_answers_even_if_header_is_long(self) -> None:
        service = VerbatimQuestionSelectionService()
        df = pd.DataFrame(
            [
                {
                    "response_id__idx_0": "1",
                    "What more could Twinkl do to improve your rating?": "10",
                },
                {
                    "response_id__idx_0": "2",
                    "What more could Twinkl do to improve your rating?": "8",
                },
                {
                    "response_id__idx_0": "3",
                    "What more could Twinkl do to improve your rating?": "9",
                },
            ]
        )

        selected_columns = service.select_columns(df, metadata_columns=["response_id__idx_0"])

        self.assertEqual(selected_columns, [])

    def test_rejects_identifier_like_columns_even_when_one_value_is_non_numeric(self) -> None:
        service = VerbatimQuestionSelectionService()
        rows = []
        for idx in range(30):
            rows.append(
                {
                    "response_id__idx_0": str(idx + 1),
                    "t_u_id__idx_10": "bad-id" if idx == 0 else str(100000 + idx),
                    "What more could Twinkl do to save you time?": f"Open answer number {idx} with varied wording.",
                }
            )
        df = pd.DataFrame(rows)

        selected_columns = service.select_columns(df, metadata_columns=["response_id__idx_0"])

        self.assertEqual(
            selected_columns,
            ["What more could Twinkl do to save you time?"],
        )

    def test_rejects_date_time_columns_as_verbatim_even_when_values_are_unique_text(self) -> None:
        service = VerbatimQuestionSelectionService()
        rows = []
        for idx in range(30):
            rows.append(
                {
                    "response_id__idx_0": str(idx + 1),
                    "Date & Time__idx_1": f"February {10 + (idx // 24)}, 2025 {idx % 24:02d}:{idx % 60:02d}:47",
                    "What more could Twinkl do to save you time?": f"Open answer number {idx} with varied wording.",
                }
            )
        df = pd.DataFrame(rows)

        selected_columns = service.select_columns(df, metadata_columns=["response_id__idx_0"])

        self.assertEqual(
            selected_columns,
            ["What more could Twinkl do to save you time?"],
        )

    def test_rejects_numeric_heavy_mixed_content_columns_as_verbatim(self) -> None:
        service = VerbatimQuestionSelectionService()
        rows = []
        for idx in range(30):
            rows.append(
                {
                    "response_id__idx_0": str(idx + 1),
                    "Submission marker__idx_1": f"Ref {20250210000000 + idx} code {10000 + idx}",
                    "What more could Twinkl do to save you time?": f"Open answer number {idx} with varied wording.",
                }
            )
        df = pd.DataFrame(rows)

        selected_columns = service.select_columns(df, metadata_columns=["response_id__idx_0"])

        self.assertEqual(
            selected_columns,
            ["What more could Twinkl do to save you time?"],
        )

    def test_selects_columns_with_short_headers_when_answers_are_text(self) -> None:
        service = VerbatimQuestionSelectionService()
        df = pd.DataFrame(
            [
                {
                    "response_id__idx_0": "1",
                    "Why Twinkl?": "It saves me time every week.",
                },
                {
                    "response_id__idx_0": "2",
                    "Why Twinkl?": "The resources are easy to adapt.",
                },
                {
                    "response_id__idx_0": "3",
                    "Why Twinkl?": "It gives me good lesson ideas.",
                },
            ]
        )

        selected_columns = service.select_columns(df, metadata_columns=["response_id__idx_0"])

        self.assertEqual(selected_columns, ["Why Twinkl?"])

    def test_selects_open_ended_short_label_columns_when_question_cues_and_variation_support_it(self) -> None:
        service = VerbatimQuestionSelectionService()
        rows = []
        brands = [
            "Teachy",
            "Canva",
            "BBC Bitesize",
            "White Rose",
            "TES",
            "Oak",
            "Kahoot",
            "Khan Academy",
            "Phonics Play",
            "ClassDojo",
            "Scratch",
            "Purple Mash",
        ]
        for idx, brand in enumerate(brands, start=1):
            rows.append(
                {
                    "response_id__idx_0": str(idx),
                    "Other than Twinkl, which ONE teaching resource brand that you use comes to mind?": brand,
                }
            )
        df = pd.DataFrame(rows)

        selected_columns = service.select_columns(df, metadata_columns=["response_id__idx_0"])

        self.assertEqual(
            selected_columns,
            ["Other than Twinkl, which ONE teaching resource brand that you use comes to mind?"],
        )

    def test_rejects_pipe_separated_headers_when_answers_are_fixed_response_text(self) -> None:
        service = VerbatimQuestionSelectionService()
        rows = []
        values = ["Yes, Twinkl is better", "No", "Yes, Twinkl is better", "Yes, Twinkl is better"]
        for idx in range(24):
            rows.append(
                {
                    "response_id__idx_0": str(idx + 1),
                    "Alignment to curriculum | Canva for Education": values[idx % len(values)],
                }
            )
        df = pd.DataFrame(rows)

        selected_columns = service.select_columns(df, metadata_columns=["response_id__idx_0"])

        self.assertEqual(selected_columns, [])

    def test_rejects_closed_question_headers_with_highly_varied_short_labels(self) -> None:
        service = VerbatimQuestionSelectionService()
        tools = [
            "ChatGPT",
            "Canva",
            "Copilot",
            "Gemini",
            "Claude",
            "Perplexity",
            "Notion AI",
            "Otter",
            "Gamma",
            "Midjourney",
            "Runway",
            "Jasper",
        ]
        df = pd.DataFrame(
            [
                {
                    "response_id__idx_0": str(idx + 1),
                    "When it comes to your work or teaching, we'd love to know your awareness and usage of the following AI tools.: I have used this AI tool within the last 6 months": tool,
                }
                for idx, tool in enumerate(tools)
            ]
        )

        selected_columns = service.select_columns(df, metadata_columns=["response_id__idx_0"])

        self.assertEqual(selected_columns, [])

    def test_selects_pipe_separated_headers_when_answers_are_highly_varied_text(self) -> None:
        service = VerbatimQuestionSelectionService()
        rows = []
        for idx in range(24):
            rows.append(
                {
                    "response_id__idx_0": str(idx + 1),
                    "Alignment to curriculum | Canva for Education": f"Varied curriculum reflection {idx} with distinct wording.",
                }
            )
        df = pd.DataFrame(rows)

        selected_columns = service.select_columns(df, metadata_columns=["response_id__idx_0"])

        self.assertEqual(selected_columns, ["Alignment to curriculum | Canva for Education"])

    def test_rejects_sparse_pipe_headers_even_when_non_blank_answers_are_distinct(self) -> None:
        service = VerbatimQuestionSelectionService()
        df = pd.DataFrame(
            [
                {
                    "response_id__idx_0": "1",
                    "Building your confidence | Lingo Kids": "The same as Twinkl",
                },
                {
                    "response_id__idx_0": "2",
                    "Building your confidence | Lingo Kids": "Better than Twinkl",
                },
                {
                    "response_id__idx_0": "3",
                    "Building your confidence | Lingo Kids": "Less well than Twinkl",
                },
                {
                    "response_id__idx_0": "4",
                    "Building your confidence | Lingo Kids": None,
                },
            ]
        )

        selected_columns = service.select_columns(df, metadata_columns=["response_id__idx_0"])

        self.assertEqual(selected_columns, [])

    def test_selects_additional_high_variation_questions_without_hardcoded_title_rules(self) -> None:
        service = VerbatimQuestionSelectionService()
        rows = []
        for idx in range(12):
            rows.append(
                {
                    "response_id__idx_0": str(idx + 1),
                    "country__idx_1": "UK" if idx % 2 == 0 else "US",
                    "What more could Twinkl do to give you confidence?": f"Confidence answer {idx}",
                    "How can Twinkl better support you to achieve excellence in your role?": f"Excellence answer {idx}",
                    "What more could Twinkl do to save you time?": f"Time answer {idx}",
                    "Thanks, we'd love to know more about why you'd recommend Twinkl": f"Recommend answer {idx}",
                    "How can we better help you see and track the progress your child is making with their learning?": f"Progress answer {idx}",
                }
            )
        df = pd.DataFrame(rows)

        selected_columns = service.select_columns(
            df,
            metadata_columns=["response_id__idx_0", "country__idx_1"],
        )

        self.assertEqual(
            selected_columns,
            [
                "What more could Twinkl do to give you confidence?",
                "How can Twinkl better support you to achieve excellence in your role?",
                "What more could Twinkl do to save you time?",
                "Thanks, we'd love to know more about why you'd recommend Twinkl",
                "How can we better help you see and track the progress your child is making with their learning?",
            ],
        )

    def test_rejects_small_sample_fixed_response_text_columns(self) -> None:
        service = VerbatimQuestionSelectionService()
        rows = []
        repeated_values = [
            "5 (Essential)",
            "5 (Essential)",
            "4",
            "5 (Essential)",
            "4",
            "5 (Essential)",
            "3",
            "5 (Essential)",
            "5 (Essential)",
            "4",
        ]
        for idx, value in enumerate(repeated_values, start=1):
            rows.append(
                {
                    "response_id__idx_0": str(idx),
                    "How important is this to you?: Confidence: Feeling assured in the quality of what I am using": value,
                }
            )
        df = pd.DataFrame(rows)

        selected_columns = service.select_columns(df, metadata_columns=["response_id__idx_0"])

        self.assertEqual(selected_columns, [])


class MetadataColumnSelectionServiceTests(unittest.TestCase):
    def test_selects_business_metadata_columns_including_dates(self) -> None:
        service = MetadataColumnSelectionService()
        df = pd.DataFrame(
            columns=[
                "response_id__idx_0",
                "user_id__idx_1",
                "started_at__idx_2",
                "completed_at__idx_3",
                "bundle__idx_4",
                "career__idx_5",
                "career_category__idx_6",
                "career_group__idx_7",
                "simplified_career__idx_8",
                "country__idx_9",
                "county__idx_10",
                "Date & Time__idx_11",
                "What more could Twinkl do to save you time?",
                "Which of the following best describes your role?",
            ]
        )

        self.assertEqual(
            service.select_columns(df),
            [
                "response_id__idx_0",
                "user_id__idx_1",
                "started_at__idx_2",
                "completed_at__idx_3",
                "bundle__idx_4",
                "career__idx_5",
                "career_category__idx_6",
                "career_group__idx_7",
                "simplified_career__idx_8",
                "country__idx_9",
                "county__idx_10",
                "Date & Time__idx_11",
            ],
        )

    def test_does_not_treat_long_question_headers_as_metadata_when_they_contain_month_or_state_substrings(self) -> None:
        service = MetadataColumnSelectionService()
        df = pd.DataFrame(
            columns=[
                "survey_month__idx_1",
                "country__idx_2",
                "group__idx_3",
                "18.2 With Regards To Science We'd Love To Know Your Awareness And Usage Of The Following Brands I Have Used This Brand Within The Last 6 Months__idx_201",
                "Which group of resources do you use most often?__idx_250",
                "27.1 To What Extent Do The Following Statements Resonate With You When You Think Of Twinkl Made By Educators__idx_301",
            ]
        )

        self.assertEqual(
            service.select_columns(df),
            [
                "survey_month__idx_1",
                "country__idx_2",
                "group__idx_3",
            ],
        )

    def test_treats_high_signal_metadata_words_as_metadata_only_when_they_stand_alone(self) -> None:
        service = MetadataColumnSelectionService()
        df = pd.DataFrame(
            columns=[
                "month__idx_1",
                "group__idx_2",
                "career__idx_3",
                "Which month did you first hear about Twinkl?__idx_10",
                "Which group best describes your needs?__idx_11",
            ]
        )

        self.assertEqual(
            service.select_columns(df),
            [
                "month__idx_1",
                "group__idx_2",
                "career__idx_3",
            ],
        )

    def test_selects_expanded_metadata_library_terms(self) -> None:
        service = MetadataColumnSelectionService()
        df = pd.DataFrame(
            columns=[
                "survey_wave__idx_1",
                "submission_date__idx_2",
                "language__idx_3",
                "locale__idx_4",
                "state_code__idx_5",
                "project_name__idx_6",
                "nps_score__idx_7",
                "segment__idx_8",
                "cohort__idx_9",
                "What language do you teach in most often?__idx_20",
                "How would you describe your cohort this year?__idx_21",
            ]
        )

        self.assertEqual(
            service.select_columns(df),
            [
                "survey_wave__idx_1",
                "submission_date__idx_2",
                "language__idx_3",
                "locale__idx_4",
                "state_code__idx_5",
                "project_name__idx_6",
                "nps_score__idx_7",
                "segment__idx_8",
                "cohort__idx_9",
            ],
        )

    def test_selects_short_identifier_style_headers_as_metadata(self) -> None:
        service = MetadataColumnSelectionService()
        df = pd.DataFrame(
            columns=[
                "t_u_id__idx_1",
                "t_s_id__idx_2",
                "t_c_id__idx_3",
                "t_ca_id__idx_4",
                "t_co_id__idx_5",
                "What more could Twinkl do to save you time?__idx_20",
            ]
        )

        self.assertEqual(
            service.select_columns(df),
            [
                "t_u_id__idx_1",
                "t_s_id__idx_2",
                "t_c_id__idx_3",
                "t_ca_id__idx_4",
                "t_co_id__idx_5",
            ],
        )

    def test_selects_name_and_email_identifier_headers_as_metadata(self) -> None:
        service = MetadataColumnSelectionService()
        df = pd.DataFrame(
            columns=[
                "name__idx_1",
                "email_address__idx_2",
                "school_name__idx_3",
                "What is the name of your favourite resource?__idx_20",
                "What more could Twinkl do to save you time?__idx_21",
            ]
        )

        self.assertEqual(
            service.select_columns(df),
            [
                "name__idx_1",
                "email_address__idx_2",
                "school_name__idx_3",
            ],
        )

    def test_selects_bq_business_metadata_columns(self) -> None:
        service = MetadataColumnSelectionService()
        df = pd.DataFrame(
            columns=[
                "response_id__idx_0",
                "survey_month__idx_1",
                "country__idx_13",
                "country_group__idx_14",
                "country_tier__idx_15",
                "career_category__idx_17",
                "career_group__idx_18",
                "sub_type__idx_19",
                "bundle__idx_20",
                "purchase_group__idx_21",
                "renewal_group__idx_22",
                "subscription_tenure__idx_23",
                "rfm_status__idx_24",
                "What more could Twinkl do to save you time?",
            ]
        )

        self.assertEqual(
            service.select_columns(df),
            [
                "response_id__idx_0",
                "survey_month__idx_1",
                "country__idx_13",
                "country_group__idx_14",
                "country_tier__idx_15",
                "career_category__idx_17",
                "career_group__idx_18",
                "sub_type__idx_19",
                "bundle__idx_20",
                "purchase_group__idx_21",
                "renewal_group__idx_22",
                "subscription_tenure__idx_23",
                "rfm_status__idx_24",
            ],
        )


class AnalysisReadyDatasetServiceTests(unittest.TestCase):
    def test_build_returns_metadata_plus_selected_verbatim_columns(self) -> None:
        text_normalizer = TextNormalizationService()
        service = AnalysisReadyDatasetService(
            metadata_selector=MetadataColumnSelectionService(),
            verbatim_selector=VerbatimQuestionSelectionService(),
            multipart_verbatim_consolidator=MultipartVerbatimConsolidationService(text_normalizer),
            row_filter=VerbatimRowFilterService(),
        )
        df = pd.DataFrame(
            [
                {
                    "response_id__idx_0": "1",
                    "user_id__idx_1": "1001",
                    "started_at__idx_2": "2026-01-01 10:00:00 UTC",
                    "country__idx_3": "UK",
                    "bundle__idx_4": "ultimate",
                    "What more could Twinkl do to save you time?": "Provide weekly packs tailored to my class.",
                    "Thanks, we'd love to know more about why you'd recommend Twinkl": "It saves me planning time every week.",
                },
                {
                    "response_id__idx_0": "2",
                    "user_id__idx_1": "1002",
                    "started_at__idx_2": "2026-01-02 10:00:00 UTC",
                    "country__idx_3": "US",
                    "bundle__idx_4": "core",
                    "What more could Twinkl do to save you time?": "Bundle the best matching resources together.",
                    "Thanks, we'd love to know more about why you'd recommend Twinkl": "The resources are easy to find and adapt.",
                },
            ]
        )

        analysis_df, metadata_columns, verbatim_columns = service.build(df)

        self.assertEqual(
            metadata_columns,
            [
                "response_id__idx_0",
                "user_id__idx_1",
                "started_at__idx_2",
                "country__idx_3",
                "bundle__idx_4",
            ],
        )
        self.assertEqual(
            verbatim_columns,
            [
                "What more could Twinkl do to save you time?",
                "Thanks, we'd love to know more about why you'd recommend Twinkl",
            ],
        )
        self.assertEqual(analysis_df.columns.tolist(), metadata_columns + verbatim_columns)

    def test_build_consolidates_word_slots_before_selecting_verbatim_columns(self) -> None:
        text_normalizer = TextNormalizationService()
        service = AnalysisReadyDatasetService(
            metadata_selector=MetadataColumnSelectionService(),
            verbatim_selector=VerbatimQuestionSelectionService(),
            multipart_verbatim_consolidator=MultipartVerbatimConsolidationService(text_normalizer),
            row_filter=VerbatimRowFilterService(),
        )
        df = pd.DataFrame(
            [
                {
                    "response_id__idx_0": "1",
                    "country__idx_1": "UK",
                    "24.1: What three words best describe the frustrations of Twinkl?: Word 1__idx_137": "Slow",
                    "24.2: What three words best describe the frustrations of Twinkl?: Word 2__idx_138": "Clunky",
                    "24.3: What three words best describe the frustrations of Twinkl?: Word 3__idx_139": "Confusing",
                },
                {
                    "response_id__idx_0": "2",
                    "country__idx_1": "US",
                    "24.1: What three words best describe the frustrations of Twinkl?: Word 1__idx_137": "Helpful",
                    "24.2: What three words best describe the frustrations of Twinkl?: Word 2__idx_138": "Creative",
                    "24.3: What three words best describe the frustrations of Twinkl?: Word 3__idx_139": "Reliable",
                },
                {
                    "response_id__idx_0": "3",
                    "country__idx_1": "CA",
                    "24.1: What three words best describe the frustrations of Twinkl?: Word 1__idx_137": "Expensive",
                    "24.2: What three words best describe the frustrations of Twinkl?: Word 2__idx_138": "Dated",
                    "24.3: What three words best describe the frustrations of Twinkl?: Word 3__idx_139": "Crowded",
                },
            ]
        )

        analysis_df, metadata_columns, verbatim_columns = service.build(df)

        self.assertEqual(
            metadata_columns,
            ["response_id__idx_0", "country__idx_1"],
        )
        self.assertEqual(
            verbatim_columns,
            ["What three words best describe the frustrations of Twinkl?"],
        )
        self.assertEqual(
            analysis_df["What three words best describe the frustrations of Twinkl?"].tolist(),
            [
                "Slow, Clunky, Confusing",
                "Helpful, Creative, Reliable",
                "Expensive, Dated, Crowded",
            ],
        )


if __name__ == "__main__":
    unittest.main()
