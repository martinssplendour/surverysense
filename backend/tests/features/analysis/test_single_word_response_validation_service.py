import json
import unittest
from unittest.mock import patch

from app.features.analysis.single_word_response_validation_service import (
    GeminiSingleWordResponseValidationService,
    SingleWordValidationConfig,
)


class _FakeHttpResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class GeminiSingleWordResponseValidationServiceTests(unittest.TestCase):
    def build_service(self, *, batch_size: int = 100) -> GeminiSingleWordResponseValidationService:
        return GeminiSingleWordResponseValidationService(
            config=SingleWordValidationConfig(
                enabled=True,
                gemini_api_key="test-key",
                gemini_model="gemini-2.5-flash",
                timeout_seconds=8,
                batch_size=batch_size,
            )
        )

    def test_classify_batches_unique_single_words_and_returns_drop_set(self) -> None:
        service = self.build_service(batch_size=2)
        calls: list[list[str]] = []

        def _fake_urlopen(request, timeout):
            self.assertEqual(timeout, 8)
            headers = {key.casefold(): value for key, value in request.header_items()}
            self.assertEqual(headers.get("x-goog-api-key"), "test-key")
            request_payload = json.loads(request.data.decode("utf-8"))
            prompt = request_payload["contents"][0]["parts"][0]["text"]
            evidence = json.loads(prompt.split("Evidence:", 1)[1])
            words = evidence["words"]
            calls.append(words)
            decisions = [
                {"word": word, "action": "delete" if word in {"cvv", "ccc"} else "keep"}
                for word in words
            ]
            return _FakeHttpResponse(
                {
                    "candidates": [
                        {"content": {"parts": [{"text": json.dumps({"decisions": decisions})}]}}
                    ]
                }
            )

        with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            result = service.classify(["CVV", "cost", "ccc", "cost"])

        self.assertEqual(calls, [["cvv", "cost"], ["ccc"]])
        self.assertEqual(result.drop_words, {"cvv", "ccc"})
        self.assertEqual(result.warnings, [])

    def test_classify_uses_cached_decisions(self) -> None:
        service = self.build_service()

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
                                                "decisions": [
                                                    {"word": "cvv", "action": "delete"},
                                                    {"word": "cost", "action": "keep"},
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

        with patch("urllib.request.urlopen", side_effect=_fake_urlopen) as mocked_urlopen:
            first = service.classify(["cvv", "cost"])
            second = service.classify(["cvv", "cost"])

        self.assertEqual(first.drop_words, {"cvv"})
        self.assertEqual(second.drop_words, {"cvv"})
        self.assertEqual(mocked_urlopen.call_count, 1)

    def test_classify_keeps_words_when_gemini_fails(self) -> None:
        service = self.build_service()

        with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
            result = service.classify(["cvv", "cost"])

        self.assertEqual(result.drop_words, set())
        self.assertIn("Single-word response validation was skipped", " ".join(result.warnings))


if __name__ == "__main__":
    unittest.main()
