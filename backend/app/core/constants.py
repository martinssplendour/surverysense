from __future__ import annotations

from app.models.enums import AnalysisModelKey

MODEL_LABELS: dict[AnalysisModelKey, str] = {
    AnalysisModelKey.BERTOPIC: "Topic Clusters",
    AnalysisModelKey.KMEANS: "Fixed Similarity Groups",
    AnalysisModelKey.HDBSCAN: "HDBSCAN",
    AnalysisModelKey.NGRAMS: "Repeated Words and Phrases",
}
