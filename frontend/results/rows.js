// Fetches and incrementally loads paginated row data from the server, supporting both the full-data and verbatim datasets.
import {
    FULL_DATA_INITIAL_VISIBLE_ROW_TARGET,
    FULL_DATA_ROW_PAGE_SIZE,
    FULL_DATA_VISIBLE_COLUMN_COUNT,
    INITIAL_VISIBLE_ROW_TARGET,
    ROW_PAGE_SIZE,
    elements,
    state,
} from "./shared.js";
import { fetchRowsPage as fetchRowsPageApi, parseJson } from "./rowsApi.js";
import {
    applyRowsPayload,
    buildRowStatusText,
    getDatasetHasMore,
    getDatasetLoadedCount,
    getDatasetTotalCount,
    resetDatasetRows,
} from "./rowsDatasetState.js";

export { parseJson };

const callbacks = {
    handleMissingResultState: () => {},
    renderAnalysisOutput: () => {},
    renderAnalysisPanel: () => {},
    renderFilterBar: () => {},
    renderPreviewTable: () => {},
    syncSliderRange: () => {},
};

export function configureResultsRows(nextCallbacks) {
    Object.assign(callbacks, nextCallbacks);
}

export async function maybeLoadMorePreviewRows() {
    const dataset = currentPreviewDataset();
    if (dataset === "analysis") {
        await maybeLoadMoreAnalysisRows();
        return;
    }
    if (!state.transformedHasMore || state.transformedLoading || !isNearBottom(elements.tableWrap)) {
        return;
    }
    await loadMoreRows("transformed");
    callbacks.renderPreviewTable(true);
}

export async function ensureDatasetRowCount(dataset, targetCount) {
    // Pull enough pages to satisfy the current viewport target, but stop once the
    // requested visible slice is covered instead of eagerly loading the full dataset.
    if (getDatasetLoadedCount(dataset) === 0 && getDatasetHasMore(dataset)) {
        await loadMoreRows(dataset, Math.min(ROW_PAGE_SIZE, targetCount));
    }

    const totalCount = getDatasetTotalCount(dataset);
    const desiredCount = Math.min(targetCount, totalCount);
    while (getDatasetLoadedCount(dataset) < desiredCount && getDatasetHasMore(dataset)) {
        const remaining = desiredCount - getDatasetLoadedCount(dataset);
        await loadMoreRows(dataset, Math.min(ROW_PAGE_SIZE, remaining));
    }
}

export async function refreshFilteredDatasets({ suppressAnalysisRender = false } = {}) {
    if (!state.resultId) {
        callbacks.renderFilterBar();
        callbacks.renderPreviewTable(false);
        return;
    }

    // Filters affect both the full transformed view and the verbatim-only view, so
    // refresh both datasets together to keep counts and row tables in sync.
    resetDatasetRows("transformed");
    resetDatasetRows("analysis");

    try {
        const [transformedPayload, analysisPayload] = await Promise.all([
            fetchRowsPage("transformed", 0, FULL_DATA_INITIAL_VISIBLE_ROW_TARGET),
            fetchRowsPage("analysis", 0, INITIAL_VISIBLE_ROW_TARGET),
        ]);
        applyRowsPayload("transformed", transformedPayload);
        applyRowsPayload("analysis", analysisPayload);
    } catch (error) {
        console.error("[Verbatim App] Failed to refresh preview rows after the filter change.", error);
    }

    callbacks.renderFilterBar();
    if (state.currentWorkspace === "data") {
        callbacks.renderPreviewTable(false);
        callbacks.syncSliderRange();
    }
    if (state.currentWorkspace === "analysis") {
        callbacks.renderAnalysisPanel();
    }
    if (state.currentWorkspace === "analysis-results" && !suppressAnalysisRender) {
        callbacks.renderAnalysisOutput();
    }
}

export function buildPreviewEmptyMessage() {
    const dataset = currentPreviewDataset();
    const isLoading = dataset === "analysis" ? state.analysisLoading : state.transformedLoading;
    if (isLoading) {
        return dataset === "analysis" ? "Loading verbatim data..." : "Loading processed data...";
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
    return state.showOnlyVerbatim ? "analysis" : "transformed";
}

function getRowPageSize(dataset) {
    return dataset === "transformed" ? FULL_DATA_ROW_PAGE_SIZE : ROW_PAGE_SIZE;
}

export function getInitialVisibleRowTarget(dataset) {
    return dataset === "transformed" ? FULL_DATA_INITIAL_VISIBLE_ROW_TARGET : INITIAL_VISIBLE_ROW_TARGET;
}

export function getVisiblePreviewColumns(columns, dataset) {
    if (dataset === "analysis") {
        return columns;
    }

    // The full transformed dataset can have many columns, so horizontal paging is
    // only applied there; the verbatim-only table always shows all available columns.
    const maxOffset = Math.max(0, columns.length - FULL_DATA_VISIBLE_COLUMN_COUNT);
    const start = Math.min(state.previewColumnOffset, maxOffset);
    state.previewColumnOffset = start;
    return columns.slice(start, start + FULL_DATA_VISIBLE_COLUMN_COUNT);
}

export async function fetchRowsPage(dataset, offset, limit) {
    return fetchRowsPageApi(dataset, offset, limit, {
        hasActiveFilters,
        handleMissingResultState: callbacks.handleMissingResultState,
    });
}

async function maybeLoadMoreAnalysisRows() {
    if (!state.analysisHasMore || state.analysisLoading || !isNearBottom(elements.tableWrap)) {
        return;
    }

    await loadMoreRows("analysis");
    if (state.showOnlyVerbatim) {
        callbacks.renderPreviewTable(true);
    }
}

async function loadMoreRows(dataset, limit = getRowPageSize(dataset)) {
    if (dataset === "transformed" && state.transformedLoading) {
        return;
    }
    if (dataset === "analysis" && state.analysisLoading) {
        return;
    }
    if (!state.resultId) {
        if (dataset === "transformed") {
            state.transformedHasMore = false;
        } else {
            state.analysisHasMore = false;
        }
        return;
    }

    const offset = dataset === "transformed" ? state.transformedRows.length : state.analysisRows.length;
    if (dataset === "transformed") {
        state.transformedLoading = true;
        updatePreviewRowStatus();
    } else {
        state.analysisLoading = true;
        updatePreviewRowStatus();
    }

    try {
        const payload = await fetchRowsPage(dataset, offset, limit);

        if (dataset === "transformed") {
            // Append pages rather than replacing so infinite scroll keeps its already
            // rendered rows while the backend serves the next slice.
            state.transformedRows = state.transformedRows.concat(payload.rows || []);
            state.transformedHasMore = Boolean(payload.has_more);
            state.transformedTotalRows = Number(payload.total_row_count || 0);
            state.transformedUnfilteredTotalRows = Number(payload.unfiltered_row_count || 0);
            if (Array.isArray(payload.column_names) && payload.column_names.length) {
                state.transformedColumnNames = payload.column_names;
            }
        } else {
            state.analysisRows = state.analysisRows.concat(payload.rows || []);
            state.analysisHasMore = Boolean(payload.has_more);
            state.analysisTotalRows = Number(payload.total_row_count || 0);
            state.analysisUnfilteredTotalRows = Number(payload.unfiltered_row_count || 0);
            if (Array.isArray(payload.column_names) && payload.column_names.length) {
                state.analysisColumnNames = payload.column_names;
            }
        }
        updatePreviewRowStatus();
    } catch (error) {
        if (dataset === "transformed") {
            state.transformedHasMore = false;
        } else {
            state.analysisHasMore = false;
        }
        console.error(
            `[Verbatim App] Failed to load ${dataset === "analysis" ? "verbatim" : "processed"} preview rows.`,
            error,
        );
    } finally {
        if (dataset === "transformed") {
            state.transformedLoading = false;
        } else {
            state.analysisLoading = false;
        }
        updatePreviewRowStatus();
    }
}

// Triggers infinite-scroll loading when the user is within 120 px of the bottom of the scrollable container.
function isNearBottom(element) {
    return (element.scrollTop + element.clientHeight) >= (element.scrollHeight - 120);
}
