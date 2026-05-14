from __future__ import annotations

from app.features.analysis.topic_analysis_services.config import PreparedDocument
from app.features.analysis.topic_analysis_services.contracts import (
    AnalysisGroupRecord,
    AnalysisNetworkEdgeRecord,
    AnalysisScatterPointRecord,
)


class CommunityPlotRecordBuilder:
    @staticmethod
    def build(
        *,
        documents: list[PreparedDocument],
        assignments: list[int],
        groups: list[AnalysisGroupRecord],
        group_id_aliases: dict[str, str] | None = None,
        noise_row_numbers: set[int] | None = None,
        layout_positions: dict[int, tuple[float, float]],
        network_edges: list[tuple[int, int, float]],
    ) -> tuple[list[AnalysisScatterPointRecord], list[AnalysisNetworkEdgeRecord]]:
        group_labels = {str(group.group_id): group.label for group in groups}
        aliases = {str(source): str(target) for source, target in (group_id_aliases or {}).items()}
        noise_rows = {int(row_number) for row_number in (noise_row_numbers or set())}
        scatter_points: list[AnalysisScatterPointRecord] = []
        row_numbers_by_node: dict[int, int] = {}
        for node_index, (document, assignment) in enumerate(zip(documents, assignments)):
            row_number = int(document.row_number)
            if row_number <= 0:
                continue
            row_numbers_by_node[node_index] = row_number
            position = layout_positions.get(node_index)
            if position is None:
                continue
            original_group_id = str(int(assignment))
            group_id = "-1" if row_number in noise_rows else aliases.get(original_group_id, original_group_id)
            scatter_points.append(
                AnalysisScatterPointRecord(
                    point_index=int(node_index),
                    row_number=row_number,
                    text=document.text,
                    source_text=document.original_text,
                    group_id=group_id,
                    group_label=group_labels.get(group_id, f"Community {original_group_id}"),
                    x=float(position[0]),
                    y=float(position[1]),
                )
            )

        edge_records: list[AnalysisNetworkEdgeRecord] = []
        for source_node, target_node, weight in network_edges:
            source_row_number = row_numbers_by_node.get(int(source_node))
            target_row_number = row_numbers_by_node.get(int(target_node))
            if source_row_number is None or target_row_number is None:
                continue
            edge_records.append(
                AnalysisNetworkEdgeRecord(
                    source_point_index=int(source_node),
                    target_point_index=int(target_node),
                    source_row_number=source_row_number,
                    target_row_number=target_row_number,
                    weight=float(weight),
                )
            )
        return scatter_points, edge_records
