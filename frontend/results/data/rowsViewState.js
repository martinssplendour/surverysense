import {
    FULL_DATA_INITIAL_VISIBLE_ROW_TARGET,
    FULL_DATA_VISIBLE_COLUMN_COUNT,
    INITIAL_VISIBLE_ROW_TARGET,
    elements,
    state,
} from "../shared.js";
import { buildRowStatusText } from "./rowsDatasetState.js";


export function buildPreviewEmptyMessage() {
    const dataset = currentPreviewDataset();
    const isLoading = dataset === "community_analysis"
        ? state.communityAnalysisLoading
        : dataset === "analysis"
            ? state.analysisLoading
            : state.transformedLoading;
    if (isLoading) {
        if (dataset === "community_analysis") {
            return "Loading community assignment data...";
        }
        return dataset === "analysis" ? "Loading verbatim data..." : "Loading processed data...";
    }
    if (dataset === "community_analysis") {
        return "No community assignment data is available. Run community detection first.";
    }
    return dataset === "analysis"
        ? "No verbatim data is available for this file."
        : "No processed data is available for this file.";
}


export function updatePreviewRowStatus() {
    elements.tableRowStatus.textContent = buildRowStatusText(currentPreviewDataset(), { hasActiveFilters });
}


export function hasActiveFilters() {
    return Object.keys(state.activeFilters).length > 0;
}


// Returns "analysis" (verbatim-only columns) or "transformed" (all columns) based on the toggle state.
export function currentPreviewDataset() {
    if (state.dataPreviewDataset === "community_analysis") {
        return "community_analysis";
    }
    return state.showOnlyVerbatim ? "analysis" : "transformed";
}


export function getInitialVisibleRowTarget(dataset) {
    return dataset === "transformed" ? FULL_DATA_INITIAL_VISIBLE_ROW_TARGET : INITIAL_VISIBLE_ROW_TARGET;
}


export function getVisiblePreviewColumns(columns, dataset) {
    if (dataset === "analysis" || dataset === "community_analysis") {
        return columns;
    }

    // The full transformed dataset can have many columns, so horizontal paging is
    // only applied there; the verbatim-only table always shows all available columns.
    const maxOffset = Math.max(0, columns.length - FULL_DATA_VISIBLE_COLUMN_COUNT);
    const start = Math.min(state.previewColumnOffset, maxOffset);
    state.previewColumnOffset = start;
    return columns.slice(start, start + FULL_DATA_VISIBLE_COLUMN_COUNT);
}
