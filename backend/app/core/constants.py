from __future__ import annotations


DEFAULT_SESSION_SECRET = "verbatim-app-dev-session-secret-change-me"

MODEL_LABELS: dict[str, str] = {
    "bertopic": "Topic Clusters",
    "kmeans": "Fixed Similarity Groups",
    "hdbscan": "HDBSCAN",
    "ngrams": "Repeated Words and Phrases",
}
