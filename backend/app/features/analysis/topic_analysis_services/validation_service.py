from __future__ import annotations

from collections.abc import Iterable

from app.core.constants import MODEL_LABELS
from app.core.exceptions import TopicAnalysisInputError
from app.models.enums import AnalysisModelKey
from app.features.analysis.topic_analysis_services.config import PreparedTextDataset


class TopicAnalysisInputValidationService:
    SUPPORTED_MODELS = frozenset(MODEL_LABELS)

    def get_model_label(self, model_key: AnalysisModelKey) -> str:
        return MODEL_LABELS[model_key]

    def validate_request(
        self,
        *,
        model_key: AnalysisModelKey,
        text_column_name: str,
        available_verbatim_columns: Iterable[str],
    ) -> None:
        if model_key not in self.SUPPORTED_MODELS:
            raise TopicAnalysisInputError(f"Unsupported analysis mode '{model_key.value}'.")

        verbatim_column_set = set(available_verbatim_columns)
        if text_column_name not in verbatim_column_set:
            raise TopicAnalysisInputError(
                "Choose one of the detected verbatim columns before running analysis."
            )

    def validate_dataset(self, prepared: PreparedTextDataset, *, model_key: AnalysisModelKey) -> list[str]:
        warnings = list(prepared.warnings)
        valid_count = len(prepared.documents)
        if valid_count == 0:
            raise TopicAnalysisInputError(
                "The selected column does not contain any usable text after removing empty and NaN values."
            )

        if model_key != AnalysisModelKey.NGRAMS:
            if valid_count < 2:
                raise TopicAnalysisInputError(
                    "This analysis mode needs at least two non-empty responses."
                )
            if prepared.unique_document_count < 2:
                raise TopicAnalysisInputError(
                    "This analysis mode needs at least two unique responses after cleaning."
                )

        if model_key == AnalysisModelKey.COMMUNITY and valid_count < 5:
            warnings.append(
                "Community detection works best with at least 5 usable responses. Smaller samples may produce weak communities."
            )
        return warnings
