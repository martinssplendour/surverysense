import { state } from "./shared.js";


export function getDatasetLoadedCount(dataset) {
    return dataset === "analysis" ? state.analysisRows.length : state.transformedRows.length;
}


export function getDatasetHasMore(dataset) {
    return dataset === "analysis" ? state.analysisHasMore : state.transformedHasMore;
}


export function getDatasetTotalCount(dataset) {
    return dataset === "analysis" ? state.analysisTotalRows : state.transformedTotalRows;
}


export function resetDatasetRows(dataset) {
    if (dataset === "transformed") {
        state.transformedRows = [];
        state.transformedHasMore = false;
        state.transformedLoading = false;
        state.transformedTotalRows = 0;
        return;
    }

    state.analysisRows = [];
    state.analysisHasMore = false;
    state.analysisLoading = false;
    state.analysisTotalRows = 0;
}


export function applyRowsPayload(dataset, payload) {
    if (dataset === "transformed") {
        state.transformedRows = Array.isArray(payload.rows) ? payload.rows : [];
        state.transformedHasMore = Boolean(payload.has_more);
        state.transformedTotalRows = Number(payload.total_row_count || 0);
        state.transformedUnfilteredTotalRows = Number(payload.unfiltered_row_count || 0);
        if (Array.isArray(payload.column_names) && payload.column_names.length) {
            state.transformedColumnNames = payload.column_names;
        }
        return;
    }

    state.analysisRows = Array.isArray(payload.rows) ? payload.rows : [];
    state.analysisHasMore = Boolean(payload.has_more);
    state.analysisTotalRows = Number(payload.total_row_count || 0);
    state.analysisUnfilteredTotalRows = Number(payload.unfiltered_row_count || 0);
    if (Array.isArray(payload.column_names) && payload.column_names.length) {
        state.analysisColumnNames = payload.column_names;
    }
}


export function buildRowStatusText(dataset, { hasActiveFilters }) {
    const loadedCount = dataset === "analysis" ? state.analysisRows.length : state.transformedRows.length;
    const totalCount = dataset === "analysis"
        ? Number(state.analysisTotalRows || 0)
        : Number(state.transformedTotalRows || 0);
    const unfilteredCount = dataset === "analysis"
        ? Number(state.analysisUnfilteredTotalRows || 0)
        : Number(state.transformedUnfilteredTotalRows || 0);
    const isLoading = dataset === "analysis" ? state.analysisLoading : state.transformedLoading;

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
