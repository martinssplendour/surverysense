// Adapts the export payload into a compact model used by the HTML preview markup.
import { displayColumnLabel } from "../../shared/utils.js";


export function buildReportPreviewModel(exportPayload) {
    const result = exportPayload.analysis_result || {};
    const groups = Array.isArray(result.groups) ? [...result.groups] : [];
    const groupSections = groups
        .sort((left, right) => Number(right.count || 0) - Number(left.count || 0) || String(left.label || "").localeCompare(String(right.label || "")))
        .slice(0, 8)
        .map((group) => {
            const terms = Array.isArray(group.terms) && group.terms.length
                ? group.terms.slice(0, 4).join(", ")
                : "no top terms available";
            const sharePercent = Math.round(Number(group.share || 0) * 100);
            const examples = Array.isArray(group.examples)
                ? group.examples.slice(0, 3).map((example) => truncatePreviewText(example.text || "", 240)).filter(Boolean)
                : [];
            return {
                label: group.label || "Unlabelled group",
                summary: `${Number(group.count || 0)} responses (${sharePercent}%). Top terms: ${terms}.`,
                examples,
            };
        });

    return {
        title: "Verbatim Analysis Report",
        subtitle: buildPreviewSubtitle(exportPayload),
        charts: Array.isArray(exportPayload.charts) ? exportPayload.charts : [],
        summaryHeading: buildPreviewSummaryHeading(result),
        summaryLines: buildPreviewSummaryLines(result, groupSections),
        groupSections,
        representativeHeading: "Representative documents (groups and top 3 responses)",
        representativeSections: groupSections
            .filter((section) => section.examples.length)
            .map((section) => [section.label, section.examples]),
    };
}


function buildPreviewSubtitle(exportPayload) {
    const result = exportPayload.analysis_result || {};
    const parts = [displayColumnLabel(result.text_column_name || "")];
    const filtersText = Array.isArray(exportPayload.active_filters)
        ? exportPayload.active_filters
            .filter((item) => Array.isArray(item.values) && item.values.length)
            .map((item) => `${item.display_name || item.column_name}: ${item.values.join(", ")}`)
            .join(" | ")
        : "";
    if (filtersText) {
        parts.push(filtersText);
    }
    parts.push(`${Number(result.filtered_row_count || 0)} rows`);
    return parts.filter(Boolean).join(" | ");
}


function buildPreviewSummaryHeading(result) {
    if (Array.isArray(result.ngram_buckets) && result.ngram_buckets.length) {
        return "Phrase summaries";
    }
    if (result.model_key === "community") {
        return "Community summaries";
    }
    return "Topic summaries";
}


function buildPreviewSummaryLines(result, groupSections) {
    if (Array.isArray(result.ngram_buckets) && result.ngram_buckets.length) {
        const findings = result.ngram_buckets.map((bucket) => {
            const items = Array.isArray(bucket.items) ? bucket.items.slice(0, 5) : [];
            const terms = items.map((item) => `${item.term} (${item.document_count} responses)`).join(", ");
            return terms ? `${bucket.label}: ${terms}` : "";
        }).filter(Boolean);
        return findings.length ? findings : ["No phrase-level findings were available for export."];
    }
    if (groupSections.length) {
        return groupSections.map((section) => `${section.label}: ${section.summary}`);
    }
    return ["The selected analysis completed without exportable topic findings."];
}


function truncatePreviewText(value, limit) {
    const normalized = String(value || "").replace(/\s+/g, " ").trim();
    if (normalized.length <= limit) {
        return normalized;
    }
    return `${normalized.slice(0, Math.max(0, limit - 3)).trim()}...`;
}
