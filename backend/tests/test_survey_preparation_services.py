import unittest

import pandas as pd
from app.services.cleaning_services import TextNormalizationService
from app.services.survey_preparation_services import (
    AnswerCoverageService,
    CareerMetadataBackfillService,
    CountryFilterService,
    FullTitleFallbackService,
    MainTitleFallbackService,
    QuestionRecordExtractionService,
    QuestionSelectionService,
    QuestionTextService,
    TitleNormalizationColumnsService,
    UserIdCastingService,
    WideSurveyPivotService,
)


class SurveyPreparationServicesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text_normalizer = TextNormalizationService()
        self.user_id_casting_service = UserIdCastingService()
        self.full_title_fallback_service = FullTitleFallbackService()
        self.main_title_fallback_service = MainTitleFallbackService()
        self.title_normalization_service = TitleNormalizationColumnsService(self.text_normalizer)
        self.wide_pivot_service = WideSurveyPivotService()
        self.question_record_extractor = QuestionRecordExtractionService(self.title_normalization_service)
        self.question_selection_service = QuestionSelectionService(self.title_normalization_service)
        self.question_text_service = QuestionTextService(self.title_normalization_service)
        self.answer_coverage_service = AnswerCoverageService()
        self.country_filter_service = CountryFilterService()
        self.backfill_service = CareerMetadataBackfillService(self.question_record_extractor)

    def _build_raw_survey_df(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "user_id": "1001",
                    "country": "United Kingdom",
                    "country_group": "EMEA",
                    "country_tier": "Tier 1",
                    "career_category": "Teacher",
                    "career_group": "Primary",
                    "main_title": "What more could Twinkl do to give you confidence?",
                    "full_title": None,
                    "answer_value": "More curriculum guidance",
                },
                {
                    "user_id": "1001",
                    "country": "United Kingdom",
                    "country_group": "EMEA",
                    "country_tier": "Tier 1",
                    "career_category": "Teacher",
                    "career_group": "Primary",
                    "main_title": "Thanks, we\u2019d love to know more about why you\u2019d recommend Twinkl",
                    "full_title": "Recommend reason",
                    "answer_value": "It saves time",
                },
                {
                    "user_id": "1002",
                    "country": "United States",
                    "country_group": "Americas",
                    "country_tier": "Tier 1",
                    "career_category": "Leader",
                    "career_group": "SLT",
                    "main_title": "What more could Twinkl do to give you confidence?",
                    "full_title": "Confidence detail",
                    "answer_value": "  ",
                },
                {
                    "user_id": "1003",
                    "country": "United Kingdom",
                    "country_group": "EMEA",
                    "country_tier": "Tier 2",
                    "career_category": "Teacher",
                    "career_group": "Secondary",
                    "main_title": "Non target question",
                    "full_title": "Non target question",
                    "answer_value": "Ignore this",
                },
            ]
        )

    def _prepare_cleaned_df(self, raw_df: pd.DataFrame) -> pd.DataFrame:
        cleaned_df = self.user_id_casting_service.cast(raw_df)
        cleaned_df = self.full_title_fallback_service.apply(cleaned_df)
        cleaned_df = self.main_title_fallback_service.apply(cleaned_df)
        cleaned_df = self.title_normalization_service.apply(cleaned_df)
        return cleaned_df

    def test_individual_cleaning_services_prepare_raw_survey_data(self) -> None:
        raw_df = self._build_raw_survey_df()
        cleaned_df = self._prepare_cleaned_df(raw_df)

        self.assertEqual(str(cleaned_df["user_id"].dtype), "Int64")
        self.assertEqual(
            cleaned_df.loc[0, "full_title_fixed"],
            "What more could Twinkl do to give you confidence?",
        )
        self.assertEqual(
            cleaned_df.loc[1, "main_title_norm"],
            "Thanks, we'd love to know more about why you'd recommend Twinkl",
        )

        wide_df = self.wide_pivot_service.build(cleaned_df)
        records_df = self.question_record_extractor.extract(
            wide_df,
            "What more could Twinkl do to give you confidence?",
        )

        self.assertEqual(len(records_df), 1)
        self.assertEqual(records_df.iloc[0]["user_id"], 1001)
        self.assertEqual(records_df.iloc[0]["career_group"], "Primary")
        self.assertEqual(records_df.iloc[0]["text"], "More curriculum guidance")

    def test_question_selection_country_filter_and_coverage_are_individual_services(self) -> None:
        raw_df = self._build_raw_survey_df()
        filtered_df = self.country_filter_service.apply(raw_df, "United Kingdom")
        cleaned_df = self._prepare_cleaned_df(filtered_df)
        wide_df = self.wide_pivot_service.build(cleaned_df)
        analysis_df = self.question_selection_service.filter_analysis_questions(wide_df)
        coverage_stats = self.answer_coverage_service.summarize(cleaned_df)

        self.assertEqual(coverage_stats["total_users"], 2)
        self.assertEqual(coverage_stats["users_with_any_answer"], 2)
        self.assertEqual(coverage_stats["users_with_no_answers"], 0)
        self.assertIn("user_id", analysis_df.columns.get_level_values(0))

        main_titles = list(analysis_df.columns.get_level_values(0))
        self.assertIn("What more could Twinkl do to give you confidence?", main_titles)
        self.assertIn("Thanks, we'd love to know more about why you'd recommend Twinkl", main_titles)
        self.assertNotIn("Non target question", main_titles)

        text_df = self.question_text_service.run(
            analysis_df,
            "Thanks, we'd love to know more about why you'd recommend Twinkl",
        )
        self.assertEqual(len(text_df), 1)
        self.assertEqual(text_df.iloc[0]["text"], "It saves time")

    def test_career_metadata_backfill_is_own_service(self) -> None:
        raw_df = self._build_raw_survey_df()
        cleaned_df = self._prepare_cleaned_df(raw_df)
        wide_df = self.wide_pivot_service.build(cleaned_df)
        records_df = self.question_record_extractor.extract(
            wide_df,
            "What more could Twinkl do to give you confidence?",
        )

        stripped_df = records_df.copy()
        stripped_df["career_group"] = pd.NA
        stripped_df["career_category"] = pd.NA

        backfilled_df = self.backfill_service.backfill(
            stripped_df,
            question_title="What more could Twinkl do to give you confidence?",
            wide_df=wide_df,
        )

        self.assertEqual(backfilled_df.iloc[0]["career_group"], "Primary")
        self.assertEqual(backfilled_df.iloc[0]["career_category"], "Teacher")


if __name__ == "__main__":
    unittest.main()
