"""K-means clustering service that automatically selects MiniBatchKMeans for large datasets."""
from __future__ import annotations

from app.core.exceptions import TopicAnalysisDependencyError


class KMeansAnalysisService:
    def run(self, embeddings, *, requested_clusters: int, random_state: int) -> dict[str, object]:
        try:
            import numpy as np
            from sklearn.cluster import KMeans, MiniBatchKMeans
        except Exception as exc:  # pragma: no cover - dependency error path
            raise TopicAnalysisDependencyError(
                "scikit-learn and numpy are required for KMeans analysis."
            ) from exc

        if getattr(embeddings, "shape", (0,))[0] == 0:
            return {"assignments": [], "warnings": []}

        n_samples = int(embeddings.shape[0])
        if n_samples == 1:
            return {
                "assignments": [0] * n_samples,
                "warnings": ["All usable responses collapsed into a single group."],
            }

        n_clusters = max(2, min(requested_clusters, n_samples))
        warnings: list[str] = []

        # MiniBatchKMeans is 3–5× faster for large datasets with negligible quality loss.
        # For small datasets, standard KMeans with elkan algorithm converges faster on
        # dense normalized vectors than the default lloyd implementation.
        if n_samples >= 1000:
            model = MiniBatchKMeans(
                n_clusters=n_clusters,
                random_state=random_state,
                n_init=3,
                batch_size=min(1024, n_samples),
            )
        else:
            model = KMeans(
                n_clusters=n_clusters,
                random_state=random_state,
                n_init=3,
                algorithm="elkan",
            )

        labels = model.fit_predict(embeddings)
        if n_clusters < requested_clusters:
            warnings.append(
                f"Fixed Similarity Groups reduced the number of groups to {n_clusters} because the filtered sample was smaller than the configured target."
            )

        return {
            "assignments": [int(value) for value in labels.tolist()],
            "warnings": warnings,
        }
