from __future__ import annotations

from collections import defaultdict

from app.features.analysis.topic_analysis_services.config import (
    PreparedDocument,
    TopicAnalysisConfig,
)
from app.features.analysis.topic_analysis_services.contracts import (
    AnalysisDocumentRecord,
    AnalysisGroupRecord,
    TopicModelGroupDefinition,
)
from app.features.analysis.topic_analysis_services.example_selection_service import (
    RepresentativeExampleSelectionService,
)
from app.features.analysis.topic_analysis_services.keyword_service import (
    TopicAnalysisKeywordService,
)
from app.features.analysis.topic_analysis_services.narrative_service import (
    TopicAnalysisNarrativeService,
)
from app.features.common.protocols import TranslationServiceProtocol


class TopicGroupAssemblyService:
    def __init__(
        self,
        *,
        config: TopicAnalysisConfig,
        keyword_service: TopicAnalysisKeywordService,
        narrative_service: TopicAnalysisNarrativeService,
        representative_example_service: RepresentativeExampleSelectionService,
        translation_service: TranslationServiceProtocol | None = None,
    ) -> None:
        self.config = config
        self.keyword_service = keyword_service
        self.narrative_service = narrative_service
        self.representative_example_service = representative_example_service
        self.translation_service = translation_service

    def build_groups(
        self,
        *,
        documents: list[PreparedDocument],
        assignments: list[int],
        explicit_groups: dict[str, TopicModelGroupDefinition],
        model_key: str,
    ) -> list[AnalysisGroupRecord]:
        grouped_documents: dict[int, list[PreparedDocument]] = defaultdict(list)
        for assignment, document in zip(assignments, documents):
            grouped_documents[int(assignment)].append(document)

        total_documents = max(1, len(documents))
        groups: list[AnalysisGroupRecord] = []
        ordered_group_ids = sorted(
            grouped_documents.keys(),
            key=lambda group_id: (-len(grouped_documents[group_id]), group_id),
        )

        fallback_prefix = "Community" if model_key == "community" else "Group"
        for group_id in ordered_group_ids:
            group_key = str(group_id)
            grouped_rows = grouped_documents[group_id]
            grouped_texts = [document.text for document in grouped_rows]
            explicit_group = explicit_groups.get(group_key, TopicModelGroupDefinition())
            terms = [str(term) for term in explicit_group.terms if term.strip()]
            terms = self.keyword_service.sanitize_terms(terms, top_n=self.config.top_terms_per_group)
            if not terms:
                terms = self.keyword_service.top_terms(grouped_texts, top_n=self.config.top_terms_per_group)

            is_noise = bool(explicit_group.is_noise or group_id == -1)
            label = self.narrative_service.build_label(
                texts=grouped_texts,
                terms=terms,
                is_noise=is_noise,
                fallback_prefix=fallback_prefix,
                fallback_id=group_key,
                prefer_terms=False,
            )
            examples = self.representative_example_service.select(
                grouped_rows,
                terms=terms,
                max_examples=self.config.representative_examples_per_group,
            )
            comment = self.narrative_service.build_comment(
                label=label,
                count=int(len(grouped_rows)),
                total_documents=total_documents,
                examples=examples,
            )
            groups.append(
                AnalysisGroupRecord(
                    group_id=group_key,
                    label=label,
                    comment=comment,
                    count=int(len(grouped_rows)),
                    share=round(len(grouped_rows) / total_documents, 4),
                    total_documents=total_documents,
                    terms=list(terms),
                    examples=examples,
                    is_noise=is_noise,
                    documents=[
                        AnalysisDocumentRecord(
                            row_number=int(document.row_number),
                            text=document.text,
                        )
                        for document in grouped_rows
                        if int(document.row_number) > 0 and document.text
                    ],
                )
            )

        return groups
