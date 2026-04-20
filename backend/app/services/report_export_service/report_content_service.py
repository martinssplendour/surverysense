from __future__ import annotations

import re
from dataclasses import dataclass

from app.models.api import AnalysisExportRequest
from app.services.service_protocols import ResultStoreReportReaderProtocol
from app.services.report_export_service._constants import _FILENAME_PATTERN
from app.services.result_store_service import ResultNotFoundError
from app.services.topic_analysis_services.contracts import (
    AnalysisExampleRecord,
    AnalysisGroupRecord,
)


@dataclass(slots=True)
class GroupSummarySection:
    label: str
    summary: str
    examples: list[str]


class ReportContentService:
    def __init__(self, result_store_service: ResultStoreReportReaderProtocol | None = None) -> None:
        self.result_store_service = result_store_service

    def build_summary_lines(self, request: AnalysisExportRequest) -> list[str]:
        result = request.analysis_result
        if result.ngram_buckets:
            findings: list[str] = []
            for bucket in result.ngram_buckets:
                top_items = bucket.items[:5]
                if not top_items:
                    continue
                lines = ", ".join(
                    f"{item.term} ({item.document_count} responses)"
                    for item in top_items
                )
                findings.append(f"{bucket.label}: {lines}")
            return findings or ["No phrase-level findings were available for export."]

        group_sections = self.build_group_summary_sections(request)
        if group_sections:
            return [f"{section.label}: {section.summary}" for section in group_sections[:8]]

        return ["The selected analysis completed without exportable topic findings."]

    def build_group_summary_sections(self, request: AnalysisExportRequest) -> list[GroupSummarySection]:
        groups = self.get_export_groups(request)
        if not groups:
            return []

        sections: list[GroupSummarySection] = []
        ordered_groups = sorted(groups, key=lambda group: (-group.count, group.label))
        for group in ordered_groups:
            share_pct = round(group.share * 100)
            terms = ", ".join(group.terms[:4]) if group.terms else "no top terms available"
            examples = [
                self.truncate_text(" ".join(example.text.split()), limit=240)
                for example in group.examples[:3]
                if example.text.strip()
            ]
            sections.append(
                GroupSummarySection(
                    label=group.label,
                    summary=f"{group.count} responses ({share_pct}%). Top terms: {terms}.",
                    examples=examples,
                )
            )
        return sections

    def get_export_groups(self, request: AnalysisExportRequest) -> list[AnalysisGroupRecord]:
        if self.result_store_service is not None:
            try:
                fast_result = self.result_store_service.get_fast_filtered_result(
                    request.analysis_result.result_id,
                    model_key=request.analysis_result.model_key,
                    text_column_name=request.analysis_result.text_column_name,
                    filters=self.build_active_filter_lookup(request),
                )
            except (ResultNotFoundError, ValueError):
                fast_result = None
            if fast_result and fast_result.groups:
                return list(fast_result.groups)
        return [
            AnalysisGroupRecord(
                group_id=group.group_id,
                label=group.label,
                source_label=group.source_label,
                translated=group.translated,
                ai_generated=group.ai_generated,
                comment=group.comment,
                count=group.count,
                share=group.share,
                terms=list(group.terms),
                examples=[
                    AnalysisExampleRecord(
                        row_number=example.row_number,
                        text=example.text,
                        source_text=example.source_text,
                        translated=example.translated,
                    )
                    for example in group.examples
                ],
                is_noise=group.is_noise,
            )
            for group in request.analysis_result.groups
        ]

    @staticmethod
    def build_active_filter_lookup(request: AnalysisExportRequest) -> dict[str, list[str]]:
        return {
            item.column_name: list(item.values)
            for item in request.active_filters
            if item.values
        }

    def build_subtitle(self, request: AnalysisExportRequest) -> str:
        parts = [self.display_column_label(request.analysis_result.text_column_name)]
        filters_text = self.filters_text(request)
        if filters_text:
            parts.append(filters_text)
        parts.append(self.row_count_text(request))
        return " | ".join(part for part in parts if part)

    @staticmethod
    def build_report_title() -> str:
        return "Verbatim Analysis Report"

    @staticmethod
    def build_summary_heading(request: AnalysisExportRequest) -> str:
        if request.analysis_result.ngram_buckets:
            return "Phrase summaries"
        return "Topic summaries"

    @staticmethod
    def build_representative_heading() -> str:
        return "Representative documents (topics and top 3 responses)"

    def build_representative_sections(self, request: AnalysisExportRequest) -> list[tuple[str, list[str]]]:
        if request.analysis_result.ngram_buckets:
            return self.build_ngram_representative_sections(request)
        return [
            (section.label, section.examples)
            for section in self.build_group_summary_sections(request)
            if section.examples
        ]

    def build_ngram_representative_sections(self, request: AnalysisExportRequest) -> list[tuple[str, list[str]]]:
        if self.result_store_service is None:
            return []

        sections: list[tuple[str, list[str]]] = []
        for bucket in request.analysis_result.ngram_buckets[:3]:
            items = list(bucket.items[:5]) if bucket.items else []
            if not items:
                continue

            selected_item = None
            examples: list[str] = []
            for item in items:
                lookup_term = (item.source_term or item.term or "").strip()
                if not lookup_term:
                    continue
                try:
                    page = self.result_store_service.get_analysis_ngram_page(
                        request.analysis_result.result_id,
                        ngram_size=int(bucket.ngram_size),
                        term=lookup_term,
                        offset=0,
                        limit=3,
                    )
                except (ResultNotFoundError, ValueError):
                    continue

                documents = page.documents
                examples = [
                    self.truncate_text(" ".join(document.text.split()), limit=240)
                    for document in documents
                    if document.text.strip()
                ]
                if examples:
                    selected_item = item
                    break

            if selected_item and examples:
                sections.append((f"{bucket.label}: {selected_item.term}", examples))
        return sections

    def build_filename_stem(self, request: AnalysisExportRequest) -> str:
        source_stem = self.strip_extension(request.source_filename or "analysis")
        method = request.analysis_result.model_label.lower().replace(" ", "-")
        return f"{source_stem}-{method}-report"

    @staticmethod
    def filters_text(request: AnalysisExportRequest) -> str:
        if not request.active_filters:
            return ""
        return " | ".join(
            f"{item.display_name or item.column_name}: {', '.join(item.values)}"
            for item in request.active_filters
            if item.values
        )

    @staticmethod
    def row_count_text(request: AnalysisExportRequest) -> str:
        return f"{int(request.analysis_result.filtered_row_count)} rows"

    @staticmethod
    def display_column_label(value: str) -> str:
        return re.sub(r"__idx_\d+$", "", value or "")

    @staticmethod
    def strip_extension(filename: str) -> str:
        value = (filename or "").strip()
        if "." not in value:
            return value
        return value.rsplit(".", 1)[0]

    @staticmethod
    def slugify(value: str) -> str:
        lowered = value.strip().lower()
        normalized = _FILENAME_PATTERN.sub("-", lowered).strip("-")
        return normalized or "analysis-report"

    @staticmethod
    def escape(value: str) -> str:
        return (
            str(value)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    @staticmethod
    def truncate_text(value: str, *, limit: int) -> str:
        normalized = " ".join((value or "").split())
        if len(normalized) <= limit:
            return normalized
        return normalized[: max(0, limit - 3)].rstrip() + "..."

    @staticmethod
    def sanitize_chart_caption(value: str | None) -> str:
        caption = " ".join((value or "").split())
        lower_caption = caption.casefold()
        interactive_phrases = (
            "hover to see",
            "click a bar",
            "matching responses",
            "matching groups responses",
            "matching topics responses",
        )
        if any(phrase in lower_caption for phrase in interactive_phrases):
            return ""
        return caption
