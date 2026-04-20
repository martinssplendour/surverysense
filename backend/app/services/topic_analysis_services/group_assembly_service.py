from __future__ import annotations

from collections import defaultdict

from app.services.service_protocols import TranslationServiceProtocol
from app.services.topic_analysis_services.config import (
    PreparedDocument,
    TopicAnalysisConfig,
)
from app.services.topic_analysis_services.contracts import (
    AnalysisDocumentRecord,
    AnalysisGroupRecord,
    TopicModelGroupDefinition,
)
from app.services.topic_analysis_services.example_selection_service import (
    RepresentativeExampleSelectionService,
)
from app.services.topic_analysis_services.keyword_service import (
    TopicAnalysisKeywordService,
)
from app.services.topic_analysis_services.narrative_service import (
    TopicAnalysisNarrativeService,
)


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

        fallback_prefix = "Topic" if model_key == "bertopic" else "Group"
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
                prefer_terms=model_key == "bertopic",
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

        if model_key == "bertopic":
            groups = self.translate_and_merge_bertopic_groups(groups)

        return groups

    def translate_and_merge_bertopic_groups(
        self, groups: list[AnalysisGroupRecord]
    ) -> list[AnalysisGroupRecord]:
        translation_service = self.translation_service

        all_terms: list[str] = []
        seen_terms: set[str] = set()
        for group in groups:
            if group.is_noise:
                continue
            for term in group.terms:
                if term and term not in seen_terms:
                    seen_terms.add(term)
                    all_terms.append(term)

        term_to_english: dict[str, str] = {t: t for t in all_terms}
        if translation_service and all_terms:
            result = translation_service.translate(all_terms)
            for source, translated, was_translated in zip(all_terms, result.texts, result.translated_flags):
                if was_translated and translated.strip():
                    term_to_english[source] = translated.strip()

        for group in groups:
            if group.is_noise:
                continue
            raw_terms = list(group.terms)
            translated_terms: list[str] = []
            seen: set[str] = set()
            for t in raw_terms:
                english = term_to_english.get(t, t)
                key = english.casefold()
                if key not in seen:
                    seen.add(key)
                    translated_terms.append(english)
            group.terms = translated_terms
            if translated_terms:
                new_label = " / ".join(t.replace("_", " ") for t in translated_terms[:2])
                if new_label != group.label:
                    group.source_label = group.label
                    group.translated = True
                    group.label = new_label

        merge_into: dict[str, str] = {}
        first_term_index: dict[str, str] = {}
        for group in groups:
            if group.is_noise:
                continue
            terms = group.terms
            if not terms:
                continue
            key = terms[0].casefold().strip().rstrip("s")
            gid = group.group_id
            if key in first_term_index:
                merge_into[gid] = first_term_index[key]
            else:
                first_term_index[key] = gid

        if merge_into:
            group_by_id = {group.group_id: group for group in groups}
            for src_id, tgt_id in merge_into.items():
                src = group_by_id[src_id]
                tgt = group_by_id[tgt_id]
                tgt.documents.extend(src.documents)
                tgt.count = int(tgt.count) + int(src.count)
            merged_ids = set(merge_into.keys())
            groups = [group for group in groups if group.group_id not in merged_ids]

        grand_total = max(1, sum(int(group.count) for group in groups))
        for group in groups:
            count = int(group.count)
            group.share = round(count / grand_total, 4)
            group.total_documents = grand_total
            group.comment = self.narrative_service.build_comment(
                label=group.label,
                count=count,
                total_documents=grand_total,
                examples=group.examples,
            )

        return sorted(groups, key=lambda group: (-int(group.count), group.group_id))
