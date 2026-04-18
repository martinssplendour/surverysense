from __future__ import annotations

from app.core.exceptions import TopicAnalysisDependencyError
from app.services.topic_analysis_services.config import PreparedDocument


class TopicScatterProjectionService:
    def __init__(self, *, random_state: int) -> None:
        self.random_state = random_state

    def build_scatter_points(
        self,
        *,
        documents: list[PreparedDocument],
        assignments: list[int],
        embeddings,
        groups: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        if not documents or not assignments:
            return []

        try:
            import numpy as np
            from sklearn.decomposition import PCA
        except Exception as exc:  # pragma: no cover - dependency error path
            raise TopicAnalysisDependencyError(
                "scikit-learn and numpy are required for K-means scatter plots."
            ) from exc

        embedding_array = np.asarray(embeddings)
        if embedding_array.ndim != 2 or embedding_array.shape[0] == 0:
            return []

        if embedding_array.shape[1] > 2 and embedding_array.shape[0] >= 2:
            projected = PCA(n_components=2, random_state=self.random_state).fit_transform(embedding_array)
        elif embedding_array.shape[1] == 2:
            projected = embedding_array
        elif embedding_array.shape[1] == 1:
            x_axis = embedding_array[:, 0]
            y_axis = np.zeros_like(x_axis)
            projected = np.column_stack((x_axis, y_axis))
        else:
            projected = np.zeros((embedding_array.shape[0], 2))

        group_labels = {
            str(group.get("group_id", "")): str(group.get("label", "Unlabelled group"))
            for group in groups
        }

        scatter_points: list[dict[str, object]] = []
        for index, (document, assignment) in enumerate(zip(documents, assignments)):
            group_key = str(int(assignment))
            scatter_points.append(
                {
                    "row_number": int(document.row_number),
                    "text": document.text,
                    "group_id": group_key,
                    "group_label": group_labels.get(group_key, "Unlabelled group"),
                    "x": round(float(projected[index, 0]), 6),
                    "y": round(float(projected[index, 1]), 6),
                }
            )
        return scatter_points
