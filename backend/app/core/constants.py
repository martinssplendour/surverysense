from __future__ import annotations

from app.models.enums import AnalysisModelKey

MODEL_LABELS: dict[AnalysisModelKey, str] = {
    AnalysisModelKey.COMMUNITY: "Community Detection",
    AnalysisModelKey.NGRAMS: "Repeated Words and Phrases",
}

COMMUNITY_GROUP_COLUMN_NAME = "community_group"
