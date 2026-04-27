import { elements, state } from "../shared.js";
import {
    displayAnalysisMode,
    displayColumnLabel,
    slugify,
    stripFilenameExtension,
} from "../shared/utils.js";


export function buildAnalysisExportTitle() {
    if (!state.analysisResult) {
        return "Verbatim Analysis Report";
    }
    return `${displayColumnLabel(state.analysisResult.text_column_name)} - ${state.analysisResult.model_label} Report`;
}


export function buildAnalysisExportFileStem() {
    const sourceName = stripFilenameExtension(state.response?.filename || "verbatim-analysis");
    const methodSlug = slugify(displayAnalysisMode(state.analysisResult?.model_key || state.selectedAnalysisModel));
    return `${slugify(sourceName)}-${methodSlug || "analysis"}-report`;
}


export function buildAnalysisExportFilters() {
    return Object.entries(state.activeFilters).map(([columnName, values]) => {
        const definition = state.availableFilters.find((item) => item.column_name === columnName) || null;
        return {
            column_name: columnName,
            display_name: definition?.display_name || definition?.column_name || columnName,
            values: Array.isArray(values) ? values : [],
        };
    });
}


export function resolveAnalysisExportDimensions({ definition, fallbackWidth, fallbackHeight }) {
    const kind = definition?.kind || "";
    if (kind === "group") {
        return {
            width: 1080,
            height: Math.max(1170, fallbackHeight),
        };
    }
    if (kind === "ngram") {
        return {
            width: 900,
            height: Math.max(900, fallbackHeight),
        };
    }

    return {
        width: fallbackWidth,
        height: fallbackHeight,
    };
}


export function buildAnalysisChartDefinitions(surfaceCount) {
    const result = state.analysisResult;
    if (!result) {
        return [];
    }
    const chartCaption = elements.analysisChart?.querySelector(".analysis-chart-caption")?.textContent?.trim() || "";
    const chartTitle = elements.analysisChart?.querySelector(".analysis-chart-title")?.textContent?.trim() || "";

    if (Array.isArray(result.ngram_buckets) && result.ngram_buckets.length) {
        return result.ngram_buckets.slice(0, surfaceCount).map((bucket) => ({
            title: bucket.label || `${bucket.ngram_size}-grams`,
            caption: chartCaption,
            kind: "ngram",
            ngramSize: Number(bucket.ngram_size || 0),
        }));
    }

    return [
        {
            title: chartTitle || `${displayAnalysisMode(result.model_key)} distribution`,
            caption: chartCaption,
            kind: "group",
        },
    ];
}
