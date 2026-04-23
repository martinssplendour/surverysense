import json
import unittest
from unittest.mock import patch

from app.models.enums import AnalysisModelKey
from app.features.analysis.topic_analysis_services.contracts import (
    AnalysisDocumentRecord,
    AnalysisExampleRecord,
    AnalysisGroupRecord,
)
from app.features.analysis.topic_label_ai_service import TopicAiLabelingConfig, TopicAiLabelService
from app.features.analysis.topic_label_evidence_builder import TopicLabelEvidenceBuilder


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


if __name__ == "__main__":
    unittest.main()
