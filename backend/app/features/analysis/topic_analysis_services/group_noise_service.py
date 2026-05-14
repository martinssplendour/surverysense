from __future__ import annotations

from app.features.analysis.topic_analysis_services.config import TopicAnalysisConfig
from app.features.analysis.topic_analysis_services.contracts import (
    AnalysisDocumentRecord,
    AnalysisExampleRecord,
    AnalysisGroupRecord,
)
from app.features.analysis.topic_analysis_services.group_post_processing_utils import refresh_group_counts
from app.features.common.document_relevance import DocumentRelevanceSorter


class TopicGroupNoiseService:
    def __init__(self, *, config: TopicAnalysisConfig) -> None:
        self.config = config

    def move_off_topic_documents_to_noise(
        self,
        groups: list[AnalysisGroupRecord],
    ) -> tuple[list[AnalysisGroupRecord], set[int], int]:
        if not groups:
            return [], set(), 0

        moved_documents_by_row: dict[int, AnalysisDocumentRecord] = {}
        for group in list(groups):
            if group.is_noise:
                continue
            documents = list(group.documents)
            if len(documents) < 2:
                continue

            keep_documents: list[AnalysisDocumentRecord] = []
            for document in documents:
                row_number = int(document.row_number)
                overlap_count = DocumentRelevanceSorter.overlap_count(
                    document.text,
                    label=group.label,
                    terms=group.terms,
                )
                if overlap_count > 0:
                    keep_documents.append(document)
                    continue
                if row_number > 0:
                    moved_documents_by_row[row_number] = document

            group.documents = keep_documents
            keep_row_numbers = {int(document.row_number) for document in keep_documents}
            group.examples = [example for example in group.examples if int(example.row_number) in keep_row_numbers]
            self._backfill_examples_from_documents(group)

        if not moved_documents_by_row:
            return self._drop_empty_non_noise_groups(groups), set(), 0

        noise_group = self._find_or_create_noise_group(groups)
        moved_documents = sorted(moved_documents_by_row.values(), key=lambda document: int(document.row_number))
        existing_noise_rows = {int(document.row_number) for document in noise_group.documents}
        for document in moved_documents:
            if int(document.row_number) not in existing_noise_rows:
                noise_group.documents.append(document)
        noise_group.documents = sorted(noise_group.documents, key=lambda document: int(document.row_number))
        self._backfill_examples_from_documents(noise_group)

        rebuilt_groups = self._drop_empty_non_noise_groups(groups)
        refresh_group_counts(rebuilt_groups)
        return rebuilt_groups, set(moved_documents_by_row), len(moved_documents_by_row)

    def _find_or_create_noise_group(self, groups: list[AnalysisGroupRecord]) -> AnalysisGroupRecord:
        for group in groups:
            if group.is_noise or str(group.group_id) == "-1":
                group.is_noise = True
                group.group_id = "-1"
                group.label = "Unassigned responses"
                return group

        noise_group = AnalysisGroupRecord(
            group_id="-1",
            label="Unassigned responses",
            is_noise=True,
            count=0,
            share=0.0,
            total_documents=0,
            terms=[],
            examples=[],
            documents=[],
        )
        groups.append(noise_group)
        return noise_group

    def _backfill_examples_from_documents(self, group: AnalysisGroupRecord) -> None:
        if len(group.examples) >= self.config.representative_examples_per_group:
            group.examples = group.examples[: self.config.representative_examples_per_group]
            return

        existing_rows = {int(example.row_number) for example in group.examples}
        for document in group.documents:
            row_number = int(document.row_number)
            if row_number in existing_rows:
                continue
            group.examples.append(
                AnalysisExampleRecord(
                    row_number=row_number,
                    text=document.text,
                )
            )
            existing_rows.add(row_number)
            if len(group.examples) >= self.config.representative_examples_per_group:
                break

    @staticmethod
    def _drop_empty_non_noise_groups(groups: list[AnalysisGroupRecord]) -> list[AnalysisGroupRecord]:
        return [
            group
            for group in groups
            if group.is_noise or group.documents
        ]
