from __future__ import annotations

from app.features.analysis.topic_analysis_services.config import TopicAnalysisConfig
from app.features.analysis.topic_analysis_services.contracts import AnalysisGroupRecord
from app.features.analysis.topic_analysis_services.group_label_merge_service import TopicGroupLabelMergeService
from app.features.analysis.topic_analysis_services.group_noise_service import TopicGroupNoiseService
from app.features.analysis.topic_analysis_services.group_post_processing_utils import compose_group_aliases
from app.features.analysis.topic_analysis_services.group_top_term_merge_service import TopicGroupTopTermMergeService
from app.features.analysis.topic_analysis_services.narrative_service import TopicAnalysisNarrativeService


class TopicGroupPostProcessingService:
    def __init__(
        self,
        *,
        config: TopicAnalysisConfig,
        narrative_service: TopicAnalysisNarrativeService,
    ) -> None:
        self.label_merge_service = TopicGroupLabelMergeService(
            config=config,
            narrative_service=narrative_service,
        )
        self.top_term_merge_service = TopicGroupTopTermMergeService(config=config)
        self.noise_service = TopicGroupNoiseService(config=config)
        self.narrative_service = narrative_service

    def merge_duplicate_label_groups(
        self,
        groups: list[AnalysisGroupRecord],
    ) -> tuple[list[AnalysisGroupRecord], dict[str, str]]:
        return self.label_merge_service.merge(groups)

    def merge_groups_by_top_term_signature(
        self,
        groups: list[AnalysisGroupRecord],
    ) -> tuple[list[AnalysisGroupRecord], dict[str, str]]:
        return self.top_term_merge_service.merge(groups)

    def move_off_topic_documents_to_noise(
        self,
        groups: list[AnalysisGroupRecord],
    ) -> tuple[list[AnalysisGroupRecord], set[int], int]:
        return self.noise_service.move_off_topic_documents_to_noise(groups)

    def refresh_group_comments(self, groups: list[AnalysisGroupRecord]) -> None:
        for group in groups:
            group.comment = self.narrative_service.build_comment(
                label=group.label or "Group",
                count=int(group.count or len(group.documents)),
                total_documents=max(1, int(group.total_documents or group.count or len(group.documents))),
                examples=list(group.examples),
            )

    @staticmethod
    def compose_group_aliases(*alias_maps: dict[str, str]) -> dict[str, str]:
        return compose_group_aliases(*alias_maps)
