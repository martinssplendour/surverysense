import json
import unittest
from unittest.mock import patch

from app.features.analysis.topic_analysis_services.contracts import (
    AnalysisDocumentRecord,
    AnalysisExampleRecord,
    AnalysisGroupRecord,
)
from app.features.analysis.topic_label_ai_service import TopicAiLabelingConfig, TopicAiLabelService
from app.features.analysis.topic_label_evidence_builder import TopicLabelEvidenceBuilder
from app.models.enums import AnalysisModelKey


class _FakeHttpResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class TopicAiLabelServiceTests(unittest.TestCase):
    def test_label_groups_returns_empty_when_service_is_disabled(self) -> None:
        service = TopicAiLabelService(
            config=TopicAiLabelingConfig(
                enabled=False,
                gemini_api_key="test-key",
                gemini_model="gemini-2.5-flash",
                gemini_temperature=0.1,
                timeout_seconds=8,
                max_groups=10,
                max_examples_per_group=3,
                max_terms_per_group=4,
                max_chars_per_example=220,
            )
        )

        result = service.label_groups(
            [{"group_id": "0", "label": "Requests for curriculum", "count": 12, "share": 0.4, "terms": [], "examples": []}],
            model_key="community",
            text_column_name="verbatim",
        )

        self.assertEqual(result.labels_by_group_id, {})
        self.assertEqual(result.warnings, [])
        self.assertEqual(result.labeled_group_count, 0)

    def test_label_groups_batches_request_and_parses_gemini_response(self) -> None:
        service = TopicAiLabelService(
            config=TopicAiLabelingConfig(
                enabled=True,
                gemini_api_key="test-key",
                gemini_model="gemini-2.5-flash",
                gemini_temperature=0.1,
                timeout_seconds=8,
                max_groups=1,
                max_examples_per_group=2,
                max_terms_per_group=3,
                max_chars_per_example=40,
            )
        )
        groups = [
            AnalysisGroupRecord(
                group_id="0",
                label="Requests for curriculum of",
                count=18,
                share=0.45,
                terms=["curriculum", "resources", "planning"],
                examples=[
                    AnalysisExampleRecord(row_number=12, text="Need more curriculum resources for maths and science"),
                    AnalysisExampleRecord(row_number=18, text="More curriculum-aligned planning materials would help"),
                ],
                documents=[
                    AnalysisDocumentRecord(row_number=12, text="Need more curriculum resources for maths and science"),
                    AnalysisDocumentRecord(row_number=18, text="More curriculum-aligned planning materials would help"),
                ],
                is_noise=False,
            ),
            AnalysisGroupRecord(
                group_id="1",
                label="Mixed or unclear responses",
                count=4,
                share=0.1,
                terms=["mixed"],
                examples=[AnalysisExampleRecord(row_number=21, text="not sure")],
                is_noise=True,
            ),
        ]

        def _fake_urlopen(request, timeout):
            self.assertEqual(timeout, 8)
            self.assertNotIn("?key=", request.full_url)
            headers = {key.casefold(): value for key, value in request.header_items()}
            self.assertEqual(headers.get("x-goog-api-key"), "test-key")
            payload = json.loads(request.data.decode("utf-8"))
            prompt = payload["contents"][0]["parts"][0]["text"]
            self.assertIn('"group_id":"0"', prompt)
            self.assertNotIn('"group_id":"1"', prompt)
            self.assertIn('"frequent_phrases"', prompt)
            self.assertIn("Need more curriculum resources for mat", prompt)
            return _FakeHttpResponse(
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": json.dumps(
                                            {"labels": [{"group_id": "0", "label": "Curriculum Resources"}]}
                                        )
                                    }
                                ]
                            }
                        }
                    ]
                }
            )

        with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            result = service.label_groups(
                groups,
                model_key=AnalysisModelKey.COMMUNITY,
                text_column_name="verbatim",
            )

        self.assertEqual(result.labels_by_group_id, {"0": "Curriculum Resources"})
        self.assertEqual(result.labeled_group_count, 1)
        self.assertEqual(result.warnings, [])

    def test_label_groups_retries_timeout_before_falling_back(self) -> None:
        service = TopicAiLabelService(
            config=TopicAiLabelingConfig(
                enabled=True,
                gemini_api_key="test-key",
                gemini_model="gemini-2.5-flash",
                gemini_temperature=0.1,
                timeout_seconds=8,
                max_groups=1,
                max_examples_per_group=2,
                max_terms_per_group=3,
                max_chars_per_example=40,
                max_retries=1,
                retry_base_seconds=0,
            )
        )
        group = AnalysisGroupRecord(
            group_id="0",
            label="Classroom Materials",
            count=3,
            share=1.0,
            terms=["classroom", "materials"],
            examples=[
                AnalysisExampleRecord(row_number=1, text="Need more classroom materials"),
                AnalysisExampleRecord(row_number=2, text="More classroom materials would help"),
            ],
            documents=[
                AnalysisDocumentRecord(row_number=1, text="Need more classroom materials"),
                AnalysisDocumentRecord(row_number=2, text="More classroom materials would help"),
            ],
        )
        calls = {"count": 0}

        def _fake_urlopen(_request, timeout):
            self.assertEqual(timeout, 8)
            calls["count"] += 1
            if calls["count"] == 1:
                raise TimeoutError("The read operation timed out")
            return _FakeHttpResponse(
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": json.dumps(
                                            {"labels": [{"group_id": "0", "label": "Classroom Materials"}]}
                                        )
                                    }
                                ]
                            }
                        }
                    ]
                }
            )

        with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            result = service.label_groups(
                [group],
                model_key=AnalysisModelKey.COMMUNITY,
                text_column_name="verbatim",
            )

        self.assertEqual(calls["count"], 2)
        self.assertEqual(result.labels_by_group_id, {"0": "Classroom Materials"})
        self.assertEqual(result.warnings, [])

    def test_label_groups_splits_large_requests_into_batches(self) -> None:
        service = TopicAiLabelService(
            config=TopicAiLabelingConfig(
                enabled=True,
                gemini_api_key="test-key",
                gemini_model="gemini-2.5-flash",
                gemini_temperature=0.1,
                timeout_seconds=8,
                max_groups=10,
                max_examples_per_group=1,
                max_terms_per_group=2,
                max_chars_per_example=80,
                batch_size=2,
                max_retries=0,
            )
        )
        groups = [
            AnalysisGroupRecord(
                group_id=str(index),
                label=f"Resource Theme {index}",
                count=3,
                share=0.3,
                terms=[f"resource {index}"],
                documents=[AnalysisDocumentRecord(row_number=index + 1, text=f"Resource {index} response")],
            )
            for index in range(3)
        ]
        calls: list[str] = []

        def _fake_urlopen(request, timeout):
            self.assertEqual(timeout, 8)
            prompt = request.data.decode("utf-8")
            calls.append(prompt)
            labels = []
            for group_id in ("0", "1", "2"):
                if f'\\"group_id\\":\\"{group_id}\\"' in prompt:
                    labels.append({"group_id": group_id, "label": f"Resource {group_id} Theme"})
            return _FakeHttpResponse({"candidates": [{"content": {"parts": [{"text": json.dumps({"labels": labels})}]}}]})

        with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            result = service.label_groups(
                groups,
                model_key=AnalysisModelKey.COMMUNITY,
                text_column_name="verbatim",
            )

        self.assertEqual(len(calls), 2)
        self.assertIn('\\"group_id\\":\\"0\\"', calls[0])
        self.assertIn('\\"group_id\\":\\"1\\"', calls[0])
        self.assertNotIn('\\"group_id\\":\\"2\\"', calls[0])
        self.assertIn('\\"group_id\\":\\"2\\"', calls[1])
        self.assertEqual(
            result.labels_by_group_id,
            {"0": "Resource 0 Theme", "1": "Resource 1 Theme", "2": "Resource 2 Theme"},
        )
        self.assertEqual(result.warnings, [])

    def test_label_groups_keeps_successful_batches_when_one_batch_fails(self) -> None:
        service = TopicAiLabelService(
            config=TopicAiLabelingConfig(
                enabled=True,
                gemini_api_key="test-key",
                gemini_model="gemini-2.5-flash",
                gemini_temperature=0.1,
                timeout_seconds=8,
                max_groups=10,
                max_examples_per_group=1,
                max_terms_per_group=2,
                max_chars_per_example=80,
                batch_size=1,
                max_retries=0,
            )
        )
        groups = [
            AnalysisGroupRecord(
                group_id=str(index),
                label=f"Resource Theme {index}",
                count=3,
                share=0.5,
                terms=[f"resource {index}"],
                documents=[AnalysisDocumentRecord(row_number=index + 1, text=f"Resource {index} response")],
            )
            for index in range(2)
        ]
        calls = {"count": 0}

        def _fake_urlopen(_request, timeout):
            self.assertEqual(timeout, 8)
            calls["count"] += 1
            if calls["count"] == 1:
                raise TimeoutError("The read operation timed out")
            return _FakeHttpResponse(
                {
                    "candidates": [
                        {"content": {"parts": [{"text": json.dumps({"labels": [{"group_id": "1", "label": "Resource 1 Theme"}]})}]}}
                    ]
                }
            )

        with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            result = service.label_groups(
                groups,
                model_key=AnalysisModelKey.COMMUNITY,
                text_column_name="verbatim",
            )

        self.assertEqual(calls["count"], 2)
        self.assertEqual(result.labels_by_group_id, {"1": "Resource 1 Theme"})
        self.assertEqual(result.labeled_group_count, 1)
        self.assertIn("1 group(s)", " ".join(result.warnings))

    def test_label_groups_rejects_placeholder_and_generic_ai_labels(self) -> None:
        service = TopicAiLabelService(
            config=TopicAiLabelingConfig(
                enabled=True,
                gemini_api_key="test-key",
                gemini_model="gemini-2.5-flash",
                gemini_temperature=0.1,
                timeout_seconds=8,
                max_groups=10,
                max_examples_per_group=2,
                max_terms_per_group=3,
                max_chars_per_example=120,
                batch_size=5,
                max_retries=0,
            )
        )
        groups = [
            AnalysisGroupRecord(
                group_id="0",
                label="Download Resources",
                count=12,
                share=0.4,
                terms=["download", "resources"],
                documents=[AnalysisDocumentRecord(row_number=1, text="Downloadable resources and materials are useful")],
            ),
            AnalysisGroupRecord(
                group_id="1",
                label="Classroom Materials",
                count=9,
                share=0.3,
                terms=["classroom", "materials"],
                documents=[AnalysisDocumentRecord(row_number=2, text="More classroom materials would help")],
            ),
            AnalysisGroupRecord(
                group_id="2",
                label="Search Filters",
                count=7,
                share=0.2,
                terms=["search", "filters"],
                documents=[AnalysisDocumentRecord(row_number=3, text="Better search filters would help")],
            ),
        ]

        def _fake_urlopen(_request, timeout):
            self.assertEqual(timeout, 8)
            return _FakeHttpResponse(
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": json.dumps(
                                            {
                                                "labels": [
                                                    {"group_id": "0", "label": "Blah Blah Blah"},
                                                    {"group_id": "1", "label": "General Feedback"},
                                                    {"group_id": "2", "label": "Search Filters"},
                                                ]
                                            }
                                        )
                                    }
                                ]
                            }
                        }
                    ]
                }
            )

        with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            result = service.label_groups(
                groups,
                model_key=AnalysisModelKey.COMMUNITY,
                text_column_name="verbatim",
            )

        self.assertEqual(result.labels_by_group_id, {"2": "Search Filters"})
        self.assertEqual(result.labeled_group_count, 1)
        self.assertIn("low-quality labels for 2 group(s)", " ".join(result.warnings))

    def test_label_groups_rejects_unsupported_short_ai_labels(self) -> None:
        service = TopicAiLabelService(
            config=TopicAiLabelingConfig(
                enabled=True,
                gemini_api_key="test-key",
                gemini_model="gemini-2.5-flash",
                gemini_temperature=0.1,
                timeout_seconds=8,
                max_groups=1,
                max_examples_per_group=2,
                max_terms_per_group=3,
                max_chars_per_example=120,
                max_retries=0,
            )
        )
        group = AnalysisGroupRecord(
            group_id="0",
            label="Download Resources",
            count=12,
            share=1.0,
            terms=["download", "resources"],
            documents=[AnalysisDocumentRecord(row_number=1, text="Downloadable resources and materials are useful")],
        )

        def _fake_urlopen(_request, timeout):
            self.assertEqual(timeout, 8)
            return _FakeHttpResponse(
                {
                    "candidates": [
                        {"content": {"parts": [{"text": json.dumps({"labels": [{"group_id": "0", "label": "Pricing Issues"}]})}]}}
                    ]
                }
            )

        with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            result = service.label_groups(
                [group],
                model_key=AnalysisModelKey.COMMUNITY,
                text_column_name="verbatim",
            )

        self.assertEqual(result.labels_by_group_id, {})
        self.assertIn("low-quality labels for 1 group(s)", " ".join(result.warnings))

    def test_evidence_builder_keeps_context_around_top_terms(self) -> None:
        builder = TopicLabelEvidenceBuilder(
            max_groups=10,
            max_examples_per_group=2,
            max_terms_per_group=4,
            max_chars_per_example=220,
        )
        group = AnalysisGroupRecord(
            group_id="0",
            label="Responses about expensive",
            count=3,
            share=1.0,
            terms=["subscription"],
            examples=[
                AnalysisExampleRecord(row_number=1, text="It is too expensive for schools"),
            ],
            documents=[
                AnalysisDocumentRecord(row_number=1, text="It is too expensive for schools"),
                AnalysisDocumentRecord(row_number=2, text="The subscription is too expensive"),
                AnalysisDocumentRecord(row_number=3, text="Expensive renewal costs are a worry"),
            ],
        )

        evidence = builder.build_group_evidence([group])

        self.assertEqual(evidence[0].terms, ["subscription"])
        self.assertIn("too expensive", evidence[0].context_phrases)
        self.assertIn("too expensive", str(evidence[0].to_prompt_payload()))

    def test_evidence_builder_uses_first_ordered_documents_without_deduping(self) -> None:
        builder = TopicLabelEvidenceBuilder(
            max_groups=10,
            max_examples_per_group=2,
            max_terms_per_group=4,
            max_chars_per_example=220,
        )
        group = AnalysisGroupRecord(
            group_id="0",
            label="Responses about resources",
            count=3,
            share=1.0,
            terms=["resources"],
            documents=[
                AnalysisDocumentRecord(row_number=1, text="Repeated response"),
                AnalysisDocumentRecord(row_number=2, text="Repeated response"),
                AnalysisDocumentRecord(row_number=3, text="Resources mentioned many times"),
            ],
        )

        evidence = builder.build_group_evidence([group])

        self.assertEqual(
            evidence[0].examples,
            ["Repeated response", "Repeated response"],
        )


if __name__ == "__main__":
    unittest.main()
