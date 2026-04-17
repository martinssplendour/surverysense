from __future__ import annotations

from app.core.exceptions import TopicAnalysisDependencyError


class HdbscanAnalysisService:
    def run(
        self,
        embeddings,
        *,
        min_cluster_size: int,
        min_samples: int,
        metric: str,
    ) -> dict[str, object]:
        try:
            import hdbscan
        except Exception as exc:  # pragma: no cover - dependency error path
            raise TopicAnalysisDependencyError(
                "hdbscan is required for density-based analysis."
            ) from exc

        if getattr(embeddings, "shape", (0,))[0] == 0:
            return {"assignments": [], "warnings": []}

        n_samples = int(embeddings.shape[0])
        cluster_size = max(2, min(min_cluster_size, n_samples))
        sample_floor = max(1, min(min_samples, cluster_size))
        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=cluster_size,
            min_samples=sample_floor,
            metric=metric,
        )
        labels = clusterer.fit_predict(embeddings)

        warnings: list[str] = []
        if all(int(label) == -1 for label in labels.tolist()):
            warnings.append(
                "Natural Groups could not find clear groups in the current filtered sample."
            )

        return {
            "assignments": [int(value) for value in labels.tolist()],
            "warnings": warnings,
        }
