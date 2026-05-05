import unittest

import pandas as pd
from app.core.constants import COMMUNITY_GROUP_COLUMN_NAME
from app.features.analysis.topic_analysis_services.contracts import (
    AnalysisDocumentRecord,
    AnalysisGroupRecord,
    AnalysisNetworkEdgeRecord,
    AnalysisNgramBucketRecord,
    AnalysisNgramItemRecord,
    AnalysisRunResult,
)
from app.features.ingestion.cleaning_services import (
    AnalysisReadyDatasetService,
    MetadataColumnSelectionService,
    MultipartVerbatimConsolidationService,
    TextNormalizationService,
    VerbatimQuestionSelectionService,
    VerbatimRowFilterService,
)
from app.features.results.metadata_filter import MetadataFilterService
from app.features.results.store import ResultNotFoundError, ResultStoreService
from app.models.enums import AnalysisModelKey


class ResultStoreServiceTests(unittest.TestCase):
    def build_service(self) -> ResultStoreService:
        text_normalizer = TextNormalizationService()
        analysis_ready_service = AnalysisReadyDatasetService(
            metadata_selector=MetadataColumnSelectionService(),
            verbatim_selector=VerbatimQuestionSelectionService(),
            multipart_verbatim_consolidator=MultipartVerbatimConsolidationService(text_normalizer),
            row_filter=VerbatimRowFilterService(),
        )
        return ResultStoreService(
            MetadataFilterService(),
            analysis_ready_service=analysis_ready_service,
            max_results=2,
        )

    def build_service_with_clock(self, *, ttl_seconds: int, clock) -> ResultStoreService:
        text_normalizer = TextNormalizationService()
        analysis_ready_service = AnalysisReadyDatasetService(
            metadata_selector=MetadataColumnSelectionService(),
            verbatim_selector=VerbatimQuestionSelectionService(),
            multipart_verbatim_consolidator=MultipartVerbatimConsolidationService(text_normalizer),
            row_filter=VerbatimRowFilterService(),
        )
        return ResultStoreService(
            MetadataFilterService(),
            analysis_ready_service=analysis_ready_service,
            max_results=2,
            ttl_seconds=ttl_seconds,
            clock=clock,
        )

    def test_save_and_get_page_returns_requested_slice(self) -> None:
        service = self.build_service()
        transformed_df = pd.DataFrame(
            [
                {"country__idx_1": "UK", "col_a": "row1", "col_b": "A"},
                {"country__idx_1": "US", "col_a": "row2", "col_b": "B"},
                {"country__idx_1": "UK", "col_a": "row3", "col_b": "C"},
            ]
        )
        analysis_df = pd.DataFrame(
            [
                {"country__idx_1": "UK", "verbatim": "v1"},
                {"country__idx_1": "US", "verbatim": "v2"},
            ]
        )

        result_id = service.save(
            transformed_df,
            analysis_df,
            metadata_columns=["country__idx_1"],
            verbatim_columns=["verbatim"],
        )
        page = service.get_page(result_id, dataset="transformed", offset=1, limit=2)

        self.assertEqual(page.result_id, result_id)
        self.assertEqual(page.dataset, "transformed")
        self.assertEqual(page.total_row_count, 3)
        self.assertEqual(page.unfiltered_row_count, 3)
        self.assertEqual(page.offset, 1)
        self.assertEqual(page.limit, 2)
        self.assertFalse(page.has_more)
        self.assertEqual(page.column_names, ["country__idx_1", "col_a", "col_b"])
        self.assertEqual(
            page.rows,
            [
                {"country__idx_1": "US", "col_a": "row2", "col_b": "B"},
                {"country__idx_1": "UK", "col_a": "row3", "col_b": "C"},
            ],
        )

    def test_get_page_can_filter_by_metadata_value(self) -> None:
        service = self.build_service()
        transformed_df = pd.DataFrame(
            [
                {"country__idx_1": "UK", "county__idx_2": "Kent", "answer": "A"},
                {"country__idx_1": "US", "county__idx_2": "King", "answer": "B"},
                {"country__idx_1": "UK", "county__idx_2": "Essex", "answer": "C"},
            ]
        )
        analysis_df = transformed_df.copy()

        result_id = service.save(
            transformed_df,
            analysis_df,
            metadata_columns=["country__idx_1", "county__idx_2"],
            verbatim_columns=["answer"],
        )
        page = service.get_page(
            result_id,
            dataset="transformed",
            offset=0,
            limit=10,
            filters={"country__idx_1": ["UK"]},
        )

        self.assertEqual(page.total_row_count, 2)
        self.assertEqual(page.unfiltered_row_count, 3)
        self.assertEqual(
            page.rows,
            [
                {"country__idx_1": "UK", "county__idx_2": "Kent", "answer": "A"},
                {"country__idx_1": "UK", "county__idx_2": "Essex", "answer": "C"},
            ],
        )

    def test_get_dataset_returns_filtered_analysis_context(self) -> None:
        service = self.build_service()
        transformed_df = pd.DataFrame(
            [
                {"country__idx_1": "UK", "verbatim": "Need more maths"},
                {"country__idx_1": "US", "verbatim": "Need more science"},
            ]
        )
        analysis_df = transformed_df.copy()

        result_id = service.save(
            transformed_df,
            analysis_df,
            metadata_columns=["country__idx_1"],
            verbatim_columns=["verbatim"],
        )
        selection = service.get_dataset(
            result_id,
            dataset="analysis",
            filters={"country__idx_1": ["UK"]},
        )

        self.assertEqual(selection.result_id, result_id)
        self.assertEqual(selection.dataset, "analysis")
        self.assertEqual(selection.total_row_count, 2)
        self.assertEqual(selection.metadata_columns, ["country__idx_1"])
        self.assertEqual(selection.verbatim_columns, ["verbatim"])
        self.assertEqual(
            selection.dataframe.to_dict(orient="records"),
            [{"country__idx_1": "UK", "verbatim": "Need more maths"}],
        )

    def test_get_page_raises_for_missing_result(self) -> None:
        service = self.build_service()

        with self.assertRaises(ResultNotFoundError):
            service.get_page("missing", dataset="analysis", offset=0, limit=10)

    def test_update_column_role_rebuilds_analysis_and_filters(self) -> None:
        service = self.build_service()
        transformed_df = pd.DataFrame(
            [
                {
                    "country__idx_1": "UK",
                    "segment__idx_2": "Primary",
                    "comment_a": "Need more phonics",
                    "comment_b": None,
                },
                {
                    "country__idx_1": "US",
                    "segment__idx_2": "Secondary",
                    "comment_a": None,
                    "comment_b": "Need more maths",
                },
            ]
        )
        analysis_df = pd.DataFrame(
            [
                {"country__idx_1": "UK", "comment_a": "Need more phonics"},
            ]
        )

        result_id = service.save(
            transformed_df,
            analysis_df,
            metadata_columns=["country__idx_1"],
            verbatim_columns=["comment_a"],
        )

        updated = service.update_column_role(
            result_id,
            column_name="segment__idx_2",
            role="metadata",
        )
        self.assertEqual(updated.metadata_columns, ["country__idx_1", "segment__idx_2"])

        updated = service.update_column_role(
            result_id,
            column_name="comment_b",
            role="verbatim",
        )
        self.assertEqual(updated.verbatim_columns, ["comment_a", "comment_b"])
        self.assertEqual(
            updated.analysis_df.to_dict(orient="records"),
            [
                {"country__idx_1": "UK", "segment__idx_2": "Primary", "comment_a": "Need more phonics", "comment_b": None},
                {"country__idx_1": "US", "segment__idx_2": "Secondary", "comment_a": None, "comment_b": "Need more maths"},
            ],
        )

    def test_get_analysis_group_page_returns_paged_group_documents(self) -> None:
        service = self.build_service()
        transformed_df = pd.DataFrame(
            [
                {"user_id__idx_1": "1001", "country__idx_1": "UK", "verbatim": "Need more maths"},
                {"user_id__idx_1": "1002", "country__idx_1": "US", "verbatim": "Need more science"},
            ]
        )
        analysis_df = transformed_df.copy()

        result_id = service.save(
            transformed_df,
            analysis_df,
            metadata_columns=["user_id__idx_1", "country__idx_1"],
            verbatim_columns=["verbatim"],
        )
        service.save_analysis_snapshot(
            result_id,
            text_column_name="verbatim",
            model_key=AnalysisModelKey.COMMUNITY,
            analysis_result=AnalysisRunResult(
                ok=True,
                result_id=result_id,
                model_key=AnalysisModelKey.COMMUNITY,
                model_label="Community Detection",
                text_column_name="verbatim",
                filtered_row_count=2,
                valid_document_count=2,
                groups=[
                    AnalysisGroupRecord(
                        group_id="0",
                        label="More Resources",
                        count=2,
                        documents=[
                            AnalysisDocumentRecord(row_number=1, text="Need more maths"),
                            AnalysisDocumentRecord(row_number=2, text="Need more science"),
                        ],
                    )
                ],
                network_edges=[
                    AnalysisNetworkEdgeRecord(source_row_number=1, target_row_number=2, weight=0.95),
                ],
            ),
        )

        page = service.get_analysis_group_page(
            result_id,
            group_id="0",
            offset=0,
            limit=1,
        )

        self.assertEqual(page.group_label, "More Resources")
        self.assertEqual(page.text_column_name, "verbatim")
        self.assertEqual(page.total_count, 2)
        self.assertTrue(page.has_more)
        self.assertEqual(
            [document.to_api_payload() for document in page.documents],
            [{"row_number": 1, "text": "Need more maths"}],
        )
        data_page = service.get_page(result_id, dataset="transformed", offset=0, limit=10)
        self.assertIn(COMMUNITY_GROUP_COLUMN_NAME, data_page.column_names)
        self.assertEqual(
            [row[COMMUNITY_GROUP_COLUMN_NAME] for row in data_page.rows],
            ["More Resources", "More Resources"],
        )
        assignment_page = service.get_page(
            result_id,
            dataset="community_analysis",
            offset=0,
            limit=10,
            filters={"country__idx_1": ["UK"]},
        )
        self.assertEqual(
            assignment_page.column_names,
            ["user_id__idx_1", "verbatim", "community_label", "community_id"],
        )
        self.assertEqual(assignment_page.total_row_count, 1)
        self.assertEqual(assignment_page.unfiltered_row_count, 2)
        self.assertEqual(
            assignment_page.rows,
            [
                {
                    "user_id__idx_1": "1001",
                    "verbatim": "Need more maths",
                    "community_label": "More Resources",
                    "community_id": "0",
                }
            ],
        )
        fast_result = service.get_fast_filtered_result(
            result_id,
            model_key=AnalysisModelKey.COMMUNITY,
            text_column_name="verbatim",
            filters={"country__idx_1": ["UK"]},
        )
        self.assertIsNotNone(fast_result)
        self.assertEqual(fast_result.original_response_count, 1)
        self.assertEqual(fast_result.network_edges, [])

    def test_community_analysis_skips_response_id_when_no_user_identifier_exists(self) -> None:
        service = self.build_service()
        transformed_df = pd.DataFrame(
            [
                {"response_id__idx_0": "resp-1", "country__idx_1": "UK", "verbatim": "Need more maths"},
                {"response_id__idx_0": "resp-2", "country__idx_1": "US", "verbatim": "Need more science"},
            ]
        )
        analysis_df = transformed_df.copy()

        result_id = service.save(
            transformed_df,
            analysis_df,
            metadata_columns=["response_id__idx_0", "country__idx_1"],
            verbatim_columns=["verbatim"],
        )
        service.save_analysis_snapshot(
            result_id,
            text_column_name="verbatim",
            model_key=AnalysisModelKey.COMMUNITY,
            analysis_result=AnalysisRunResult(
                ok=True,
                result_id=result_id,
                model_key=AnalysisModelKey.COMMUNITY,
                model_label="Community Detection",
                text_column_name="verbatim",
                filtered_row_count=2,
                valid_document_count=2,
                groups=[
                    AnalysisGroupRecord(
                        group_id="0",
                        label="More Resources",
                        count=2,
                        documents=[
                            AnalysisDocumentRecord(row_number=1, text="Need more maths"),
                            AnalysisDocumentRecord(row_number=2, text="Need more science"),
                        ],
                    )
                ],
            ),
        )

        assignment_page = service.get_page(
            result_id,
            dataset="community_analysis",
            offset=0,
            limit=10,
        )

        self.assertEqual(
            assignment_page.column_names,
            ["verbatim", "community_label", "community_id"],
        )
        self.assertEqual(
            assignment_page.rows,
            [
                {
                    "verbatim": "Need more maths",
                    "community_label": "More Resources",
                    "community_id": "0",
                },
                {
                    "verbatim": "Need more science",
                    "community_label": "More Resources",
                    "community_id": "0",
                },
            ],
        )

    def test_get_analysis_ngram_page_returns_paged_matching_documents(self) -> None:
        service = self.build_service()
        transformed_df = pd.DataFrame(
            [
                {"country__idx_1": "UK", "verbatim": "Need more maths resources"},
                {"country__idx_1": "US", "verbatim": "Need more science resources"},
            ]
        )
        analysis_df = transformed_df.copy()

        result_id = service.save(
            transformed_df,
            analysis_df,
            metadata_columns=["country__idx_1"],
            verbatim_columns=["verbatim"],
        )
        service.save_analysis_snapshot(
            result_id,
            text_column_name="verbatim",
            model_key=AnalysisModelKey.NGRAMS,
            analysis_result=AnalysisRunResult(
                ok=True,
                result_id=result_id,
                model_key=AnalysisModelKey.NGRAMS,
                model_label="Repeated words and phrases",
                text_column_name="verbatim",
                filtered_row_count=2,
                valid_document_count=2,
                ngram_buckets=[
                    AnalysisNgramBucketRecord(
                        label="Two-Word Phrases",
                        ngram_size=2,
                        items=[
                            AnalysisNgramItemRecord(
                                term="more resources",
                                source_term=None,
                                count=2,
                                document_count=2,
                                documents=[
                                    AnalysisDocumentRecord(row_number=1, text="Need more maths resources"),
                                    AnalysisDocumentRecord(row_number=2, text="Need more science resources"),
                                ],
                            )
                        ],
                    )
                ],
            ),
        )

        page = service.get_analysis_ngram_page(
            result_id,
            ngram_size=2,
            term="more resources",
            offset=0,
            limit=1,
        )

        self.assertEqual(page.term, "more resources")
        self.assertEqual(page.ngram_size, 2)
        self.assertEqual(page.text_column_name, "verbatim")
        self.assertEqual(page.total_count, 2)
        self.assertEqual(page.hit_count, 2)
        self.assertTrue(page.has_more)
        self.assertEqual(
            [document.to_api_payload() for document in page.documents],
            [{"row_number": 1, "text": "Need more maths resources"}],
        )

    def test_delete_removes_saved_result_and_analysis_snapshot(self) -> None:
        service = self.build_service()
        transformed_df = pd.DataFrame(
            [
                {"country__idx_1": "UK", "verbatim": "Need more maths"},
            ]
        )
        analysis_df = transformed_df.copy()

        result_id = service.save(
            transformed_df,
            analysis_df,
            metadata_columns=["country__idx_1"],
            verbatim_columns=["verbatim"],
        )
        service.save_analysis_snapshot(
            result_id,
            text_column_name="verbatim",
            model_key=AnalysisModelKey.COMMUNITY,
            analysis_result=AnalysisRunResult(
                ok=True,
                result_id=result_id,
                model_key=AnalysisModelKey.COMMUNITY,
                model_label="Community Detection",
                text_column_name="verbatim",
                filtered_row_count=1,
                valid_document_count=1,
                groups=[
                    AnalysisGroupRecord(
                        group_id="0",
                        label="More Resources",
                        count=1,
                        documents=[
                            AnalysisDocumentRecord(row_number=1, text="Need more maths"),
                        ],
                    )
                ],
            ),
        )

        self.assertTrue(service.delete(result_id))
        self.assertFalse(service.delete(result_id))

        with self.assertRaises(ResultNotFoundError):
            service.get_page(result_id, dataset="analysis", offset=0, limit=10)

        with self.assertRaises(ResultNotFoundError):
            service.get_analysis_group_page(result_id, group_id="0", offset=0, limit=10)

    def test_expired_result_removes_dataset_and_analysis_snapshot(self) -> None:
        current_time = 1000.0
        service = self.build_service_with_clock(
            ttl_seconds=7200,
            clock=lambda: current_time,
        )
        transformed_df = pd.DataFrame(
            [
                {"country__idx_1": "UK", "verbatim": "Need more maths"},
            ]
        )
        analysis_df = transformed_df.copy()

        result_id = service.save(
            transformed_df,
            analysis_df,
            metadata_columns=["country__idx_1"],
            verbatim_columns=["verbatim"],
        )
        service.save_analysis_snapshot(
            result_id,
            text_column_name="verbatim",
            model_key=AnalysisModelKey.COMMUNITY,
            analysis_result=AnalysisRunResult(
                ok=True,
                result_id=result_id,
                model_key=AnalysisModelKey.COMMUNITY,
                model_label="Community Detection",
                text_column_name="verbatim",
                filtered_row_count=1,
                valid_document_count=1,
                groups=[
                    AnalysisGroupRecord(
                        group_id="0",
                        label="More Resources",
                        count=1,
                        documents=[
                            AnalysisDocumentRecord(row_number=1, text="Need more maths"),
                        ],
                    )
                ],
            ),
        )

        current_time += 7201

        with self.assertRaises(ResultNotFoundError):
            service.get_page(result_id, dataset="analysis", offset=0, limit=10)

        with self.assertRaises(ResultNotFoundError):
            service.get_analysis_group_page(result_id, group_id="0", offset=0, limit=10)

    def test_cleanup_expired_purges_expired_results_without_waiting_for_next_request(self) -> None:
        current_time = 1000.0
        service = self.build_service_with_clock(
            ttl_seconds=900,
            clock=lambda: current_time,
        )
        frame = pd.DataFrame([{"country__idx_1": "UK", "verbatim": "Need more maths"}])

        result_id = service.save(
            frame,
            frame,
            metadata_columns=["country__idx_1"],
            verbatim_columns=["verbatim"],
        )

        current_time += 901

        self.assertEqual(service.cleanup_expired(), 1)
        self.assertEqual(service.cleanup_expired(), 0)
        with self.assertRaises(ResultNotFoundError):
            service.get_page(result_id, dataset="analysis", offset=0, limit=10)

    def test_lru_eviction_removes_saved_timestamp(self) -> None:
        current_time = 1000.0
        service = self.build_service_with_clock(
            ttl_seconds=7200,
            clock=lambda: current_time,
        )
        frame = pd.DataFrame([{"country__idx_1": "UK", "verbatim": "Need more maths"}])

        first_id = service.save(
            frame,
            frame,
            metadata_columns=["country__idx_1"],
            verbatim_columns=["verbatim"],
        )
        current_time += 1
        second_id = service.save(
            frame,
            frame,
            metadata_columns=["country__idx_1"],
            verbatim_columns=["verbatim"],
        )
        current_time += 1
        third_id = service.save(
            frame,
            frame,
            metadata_columns=["country__idx_1"],
            verbatim_columns=["verbatim"],
        )

        self.assertNotIn(first_id, service._saved_at)
        self.assertIn(second_id, service._saved_at)
        self.assertIn(third_id, service._saved_at)

    def test_save_with_same_owner_deletes_previous_result_and_snapshot(self) -> None:
        service = self.build_service()
        frame = pd.DataFrame([{"country__idx_1": "UK", "verbatim": "Need more maths"}])

        first_id = service.save(
            frame,
            frame,
            metadata_columns=["country__idx_1"],
            verbatim_columns=["verbatim"],
            owner_key="USER@example.com",
        )
        service.save_analysis_snapshot(
            first_id,
            text_column_name="verbatim",
            model_key=AnalysisModelKey.COMMUNITY,
            analysis_result=AnalysisRunResult(
                ok=True,
                result_id=first_id,
                model_key=AnalysisModelKey.COMMUNITY,
                model_label="Community Detection",
                text_column_name="verbatim",
                filtered_row_count=1,
                valid_document_count=1,
                groups=[
                    AnalysisGroupRecord(
                        group_id="0",
                        label="More Resources",
                        count=1,
                        documents=[
                            AnalysisDocumentRecord(row_number=1, text="Need more maths"),
                        ],
                    )
                ],
            ),
        )

        second_id = service.save(
            frame,
            frame,
            metadata_columns=["country__idx_1"],
            verbatim_columns=["verbatim"],
            owner_key="user@example.com",
        )

        self.assertNotEqual(first_id, second_id)
        with self.assertRaises(ResultNotFoundError):
            service.get_page(first_id, dataset="analysis", offset=0, limit=10)
        with self.assertRaises(ResultNotFoundError):
            service.get_analysis_group_page(first_id, group_id="0", offset=0, limit=10)
        self.assertEqual(service._owner_result_ids, {"user@example.com": second_id})

    def test_delete_removes_owner_tracking(self) -> None:
        service = self.build_service()
        frame = pd.DataFrame([{"country__idx_1": "UK", "verbatim": "Need more maths"}])

        result_id = service.save(
            frame,
            frame,
            metadata_columns=["country__idx_1"],
            verbatim_columns=["verbatim"],
            owner_key="user@example.com",
        )

        self.assertTrue(service.delete(result_id))
        self.assertEqual(service._owner_result_ids, {})
        self.assertEqual(service._result_owners, {})


if __name__ == "__main__":
    unittest.main()
