import {
    applyDatasetPayload as applyDatasetPayloadState,
    resetDatasetState,
    state,
} from "../shared.js";


export function getDatasetLoadedCount(dataset) {
    if (dataset === "community_analysis") {
        return state.communityAnalysisRows.length;
    }
    return dataset === "analysis" ? state.analysisRows.length : state.transformedRows.length;
}


export function getDatasetHasMore(dataset) {
    if (dataset === "community_analysis") {
        return state.communityAnalysisHasMore;
    }
    return dataset === "analysis" ? state.analysisHasMore : state.transformedHasMore;
}


export function getDatasetTotalCount(dataset) {
    if (dataset === "community_analysis") {
        return state.communityAnalysisTotalRows;
    }
    return dataset === "analysis" ? state.analysisTotalRows : state.transformedTotalRows;
}


export function resetDatasetRows(dataset) {
    resetDatasetState(dataset);
}


export function applyRowsPayload(dataset, payload) {
    applyDatasetPayloadState(dataset, payload);
}


export function buildRowStatusText(dataset, { hasActiveFilters }) {
    const rows = dataset === "community_analysis"
        ? state.communityAnalysisRows
        : dataset === "analysis"
            ? state.analysisRows
            : state.transformedRows;
    const loadedCount = rows.length;
    const totalCount = dataset === "community_analysis"
        ? Number(state.communityAnalysisTotalRows || 0)
        : dataset === "analysis"
            ? Number(state.analysisTotalRows || 0)
            : Number(state.transformedTotalRows || 0);
    const unfilteredCount = dataset === "community_analysis"
        ? Number(state.communityAnalysisUnfilteredTotalRows || 0)
        : dataset === "analysis"
            ? Number(state.analysisUnfilteredTotalRows || 0)
            : Number(state.transformedUnfilteredTotalRows || 0);
    const isLoading = dataset === "community_analysis"
        ? state.communityAnalysisLoading
        : dataset === "analysis"
            ? state.analysisLoading
            : state.transformedLoading;

    if (!totalCount && !loadedCount) {
        if (hasActiveFilters()) {
            return `Loaded 0 of 0 rows | filtered from ${unfilteredCount}`;
        }
        return "Loaded 0 rows";
    }

    let text = `Loaded ${loadedCount} of ${totalCount} rows`;
    if (hasActiveFilters()) {
        text += ` | filtered from ${unfilteredCount}`;
    }
    if (isLoading) {
        text += " | loading more";
    }
    return text;
}
