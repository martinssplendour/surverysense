from __future__ import annotations

import logging

from app.models.enums import AnalysisModelKey
from app.services.service_protocols import (
    TopicLabelServiceProtocol,
    TranslationServiceProtocol,
)
from app.services.topic_analysis_services.contracts import (
    AnalysisExampleRecord,
    AnalysisGroupRecord,
    AnalysisNgramBucketRecord,
    AnalysisNgramItemRecord,
)
from app.services.topic_analysis_services.keyword_service import (
    TopicAnalysisKeywordService,
)
from app.services.topic_analysis_services.narrative_service import (
    TopicAnalysisNarrativeService,
)

logger = logging.getLogger(__name__)


class TopicAnalysisOutputTranslationService:
    def __init__(
        self,
        *,
        keyword_service: TopicAnalysisKeywordService,
        narrative_service: TopicAnalysisNarrativeService,
        translation_service: TranslationServiceProtocol | None = None,
        ai_label_service: TopicLabelServiceProtocol | None = None,
    ) -> None:
        self.keyword_service = keyword_service
        self.narrative_service = narrative_service
        self.translation_service = translation_service
        self.ai_label_service = ai_label_service

    @staticmethod
    def sample_group_texts(grouped_texts: list[str], *, limit: int) -> list[str]:
        unique_texts: list[str] = []
        seen: set[str] = set()
        for text in grouped_texts:
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            unique_texts.append(text)
            if len(unique_texts) >= limit:
                break
        return unique_texts

    def apply_ai_labels(
        self,
        groups: list[AnalysisGroupRecord],
        *,
        model_key: AnalysisModelKey,
        text_column_name: str,
    ) -> tuple[int, list[str]]:
        if self.ai_label_service is None or not groups:
            return 0, []

        try:
            result = self.ai_label_service.label_groups(
                groups,
                model_key=model_key,
                text_column_name=text_column_name,
            )
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.warning(
                "AI topic labeling failed unexpectedly for model=%s column=%s (%s: %s).",
                model_key.value,
                text_column_name,
                type(exc).__name__,
                exc,
            )
            return 0, ["AI topic labeling was skipped and heuristic labels were kept."]

        relabeled_count = 0
        for group in groups:
            group_id = group.group_id.strip()
            new_label = result.labels_by_group_id.get(group_id, "").strip()
            current_label = group.label.strip()
            if not new_label or not current_label or new_label == current_label:
                continue

            group.source_label = current_label
            group.label = new_label
            group.translated = False
            group.ai_generated = True
            relabeled_count += 1

        self._refresh_group_comments(groups)

        warnings = list(result.warnings)
        if relabeled_count:
            warnings.append(f"AI generated clearer labels for {relabeled_count} group(s).")
        return relabeled_count, warnings

    def translate_group_outputs(self, groups: list[AnalysisGroupRecord]) -> tuple[int, list[str]]:
        translation_service = self.translation_service
        if translation_service is None or not groups:
            return 0, []

        warnings: list[str] = []
        translated_label_count = sum(1 for group in groups if bool(group.translated))
        translated_example_count = 0
        for group in groups:
            warnings.extend(
                message
                for message in group.label_translation_warnings
                if message.strip()
            )
            group.label_translation_warnings = []

        untranslated_groups = [
            group
            for group in groups
            if not group.translated and not group.ai_generated
        ]
        if untranslated_groups:
            label_texts = [group.label.strip() for group in untranslated_groups]
            label_result = translation_service.translate(label_texts)
            warnings.extend(label_result.warnings)
            for group, source_label, translated_label, translated_flag in zip(
                untranslated_groups,
                label_texts,
                label_result.texts,
                label_result.translated_flags,
            ):
                if translated_flag and translated_label.strip():
                    group.source_label = source_label
                    group.label = translated_label.strip()
                    group.translated = True
                    translated_label_count += 1
                else:
                    group.source_label = None
                    group.translated = False

        example_records: list[AnalysisExampleRecord] = []
        example_texts: list[str] = []
        for group in groups:
            for example in group.examples:
                example_text = example.text.strip()
                if not example_text:
                    continue
                example_records.append(example)
                example_texts.append(example_text)

        if example_texts:
            example_result = translation_service.translate(example_texts)
            warnings.extend(example_result.warnings)
            for example, source_text, translated_text, translated_flag in zip(
                example_records,
                example_texts,
                example_result.texts,
                example_result.translated_flags,
            ):
                if translated_flag and translated_text.strip():
                    example.source_text = source_text
                    example.text = translated_text.strip()
                    example.translated = True
                    translated_example_count += 1
                else:
                    example.source_text = None
                    example.translated = False

        self._refresh_group_comments(groups)

        translated_count = translated_label_count + translated_example_count
        if translated_count:
            warnings.append(
                f"Translated {translated_label_count} group label(s) and {translated_example_count} representative response(s) to English for display after grouping."
            )
        return translated_count, warnings

    def translate_ngram_buckets(self, buckets: list[AnalysisNgramBucketRecord]) -> tuple[int, list[str]]:
        translation_service = self.translation_service
        if translation_service is None or not buckets:
            return 0, []

        warnings: list[str] = []
        items: list[AnalysisNgramItemRecord] = []
        texts: list[str] = []
        for bucket in buckets:
            for item in bucket.items:
                term = item.term.strip()
                if not term:
                    continue
                items.append(item)
                texts.append(term)

        if not texts:
            return 0, []

        translation_result = translation_service.translate(texts)
        warnings.extend(translation_result.warnings)

        translated_count = 0
        for item, source_term, translated_term, translated_flag in zip(
            items,
            texts,
            translation_result.texts,
            translation_result.translated_flags,
        ):
            cleaned_translation = self.keyword_service.sanitize_terms([translated_term], top_n=1)
            display_term = cleaned_translation[0] if cleaned_translation else translated_term.strip()
            if translated_flag and display_term:
                item.source_term = source_term
                item.term = display_term
                item.translated = True
                translated_count += 1
            else:
                item.source_term = None
                item.translated = False

        if translated_count:
            warnings.append(
                f"Translated {translated_count} common phrase(s) to English for display after analysis."
            )
        return translated_count, warnings

    def _refresh_group_comments(self, groups: list[AnalysisGroupRecord]) -> None:
        for group in groups:
            count = int(group.count)
            total_documents = max(1, int(group.total_documents or count))
            group.comment = self.narrative_service.build_comment(
                label=group.label or "Group",
                count=count,
                total_documents=total_documents,
                examples=list(group.examples),
            )
