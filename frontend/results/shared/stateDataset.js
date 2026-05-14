import { cloneArray, datasetKey, state } from "./stateCore.js";

export function applyDatasetPayload(dataset, payload = {}) {
    const key = datasetKey(dataset);
    const target = state.dataset[key];
    target.rows = cloneArray(payload.rows);
    target.hasMore = Boolean(payload.has_more);
    target.totalRows = Number(payload.total_row_count || 0);
    target.unfilteredTotalRows = Number(payload.unfiltered_row_count || 0);
    if (Array.isArray(payload.column_names) && (dataset === "community_analysis" || payload.column_names.length)) {
        state.columns[key === "communityAnalysis" ? "communityAnalysis" : key] = [...payload.column_names];
    }
}

export function appendDatasetPayload(dataset, payload = {}) {
    const key = datasetKey(dataset);
    const target = state.dataset[key];
    target.rows = target.rows.concat(cloneArray(payload.rows));
    target.hasMore = Boolean(payload.has_more);
    target.totalRows = Number(payload.total_row_count || 0);
    target.unfilteredTotalRows = Number(payload.unfiltered_row_count || 0);
    if (Array.isArray(payload.column_names) && (dataset === "community_analysis" || payload.column_names.length)) {
        state.columns[key === "communityAnalysis" ? "communityAnalysis" : key] = [...payload.column_names];
    }
}

export function setDatasetStatus(dataset, nextState = {}) {
    const target = state.dataset[datasetKey(dataset)];
    if ("loading" in nextState) {
        target.loading = Boolean(nextState.loading);
    }
    if ("hasMore" in nextState) {
        target.hasMore = Boolean(nextState.hasMore);
    }
}

export function resetDatasetState(dataset) {
    const target = state.dataset[datasetKey(dataset)];
    target.rows = [];
    target.totalRows = 0;
    target.unfilteredTotalRows = 0;
    target.hasMore = false;
    target.loading = false;
}
