from __future__ import annotations

import json
import urllib.request
from typing import Any

from app.models.enums import AnalysisModelKey
from app.features.analysis.topic_analysis_services.contracts import TopicLabelEvidenceGroup


class GeminiTopicLabelClient:
    def __init__(self, *, api_key: str, model: str, temperature: float, timeout_seconds: int, prompt_builder: Any) -> None:
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.timeout_seconds = timeout_seconds
        self.prompt_builder = prompt_builder

    def request_labels(
        self,
        groups: list[TopicLabelEvidenceGroup],
        *,
        model_key: AnalysisModelKey,
        text_column_name: str,
    ) -> dict[str, Any]:
        endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        request_payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": self.prompt_builder.build_prompt(
                                groups,
                                model_key=model_key,
                                text_column_name=text_column_name,
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {
                "temperature": self.temperature,
                "responseMimeType": "application/json",
                "responseSchema": self.prompt_builder.gemini_response_schema(),
            },
        }
        payload = json.dumps(request_payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Gemini did not return a JSON object.")
        return payload
