// Fetches and incrementally loads paginated row data from the server, supporting both the full-data and verbatim datasets.
import {
    FULL_DATA_INITIAL_VISIBLE_ROW_TARGET,
    FULL_DATA_ROW_PAGE_SIZE,
    FULL_DATA_VISIBLE_COLUMN_COUNT,
    INITIAL_VISIBLE_ROW_TARGET,
    RESULT_STORAGE_KEY,
    ROW_PAGE_SIZE,
    elements,
    state,
} from "./shared.js";

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

function getDatasetLoadedCount(dataset) {
    return dataset === "analysis" ? state.analysisRows.length : state.transformedRows.length;
}

function getDatasetHasMore(dataset) {
    return dataset === "analysis" ? state.analysisHasMore : state.transformedHasMore;
}

function getDatasetTotalCount(dataset) {
    return dataset === "analysis" ? state.analysisTotalRows : state.transformedTotalRows;
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
    elements.tableRowStatus.textContent = buildRowStatusText(currentPreviewDataset());
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

function resetDatasetRows(dataset) {
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

function applyRowsPayload(dataset, payload) {
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

export async function fetchRowsPage(dataset, offset, limit) {
    const query = new URLSearchParams({
        dataset,
        offset: `${offset}`,
        limit: `${limit}`,
    });
    if (hasActiveFilters()) {
        query.set("filters", JSON.stringify(state.activeFilters));
    }

    const response = await fetch(`/result-rows/${encodeURIComponent(state.resultId)}?${query.toString()}`);
    if (response.status === 401) {
        sessionStorage.removeItem(RESULT_STORAGE_KEY);
        window.location.assign("/login");
        throw new Error("Session expired.");
    }
    if (response.status === 404) {
        const payload = await parseJson(response);
        callbacks.handleMissingResultState(payload.detail || "The processed result is no longer available.");
        throw new Error("The processed result is no longer available.");
    }

    const payload = await parseJson(response);
    if (!response.ok) {
        throw new Error(payload.detail || "Unable to load rows.");
    }
    return payload;
}

export async function parseJson(response) {
    try {
        return await response.json();
    } catch {
        return {};
    }
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

function buildRowStatusText(dataset) {
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

// Triggers infinite-scroll loading when the user is within 120 px of the bottom of the scrollable container.
function isNearBottom(element) {
    return (element.scrollTop + element.clientHeight) >= (element.scrollHeight - 120);
}
