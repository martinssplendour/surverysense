// Public row-data API: orchestrates paginated row loading and exposes narrow table state helpers.
import {
    FULL_DATA_INITIAL_VISIBLE_ROW_TARGET,
    FULL_DATA_ROW_PAGE_SIZE,
    INITIAL_VISIBLE_ROW_TARGET,
    ROW_PAGE_SIZE,
    elements,
    setDatasetStatus,
    state,
} from "../shared.js";
import { fetchRowsPage as fetchRowsPageApi, parseJson } from "./rowsApi.js";
import {
    applyRowsPayload,
    appendRowsPayload,
    getDatasetHasMore,
    getDatasetLoadedCount,
    getDatasetTotalCount,
    resetDatasetRows,
} from "./rowsDatasetState.js";
import {
    currentPreviewDataset,
    hasActiveFilters,
    updatePreviewRowStatus,
} from "./rowsViewState.js";

export { parseJson };
export {
    buildPreviewEmptyMessage,
    currentPreviewDataset,
    getInitialVisibleRowTarget,
    getVisiblePreviewColumns,
    hasActiveFilters,
    updatePreviewRowStatus,
} from "./rowsViewState.js";

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
    if (dataset === "community_analysis") {
        await maybeLoadMoreCommunityAnalysisRows();
        return;
    }
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
    // refresh the visible data views together to keep counts and row tables in sync.
    resetDatasetRows("transformed");
    resetDatasetRows("analysis");
    resetDatasetRows("community_analysis");

    try {
        const requests = [
            fetchRowsPage("transformed", 0, FULL_DATA_INITIAL_VISIBLE_ROW_TARGET),
            fetchRowsPage("analysis", 0, INITIAL_VISIBLE_ROW_TARGET),
        ];
        if (state.analysisResult?.model_key === "community") {
            requests.push(fetchRowsPage("community_analysis", 0, INITIAL_VISIBLE_ROW_TARGET));
        }
        const [transformedPayload, analysisPayload, communityAnalysisPayload] = await Promise.all(requests);
        applyRowsPayload("transformed", transformedPayload);
        applyRowsPayload("analysis", analysisPayload);
        if (communityAnalysisPayload) {
            applyRowsPayload("community_analysis", communityAnalysisPayload);
        }
    } catch (error) {
        console.error("[SurveySense] Failed to refresh preview rows after the filter change.", error);
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

function getRowPageSize(dataset) {
    return dataset === "transformed" ? FULL_DATA_ROW_PAGE_SIZE : ROW_PAGE_SIZE;
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

async function maybeLoadMoreCommunityAnalysisRows() {
    if (!state.communityAnalysisHasMore || state.communityAnalysisLoading || !isNearBottom(elements.tableWrap)) {
        return;
    }

    await loadMoreRows("community_analysis");
    if (state.dataPreviewDataset === "community_analysis") {
        callbacks.renderPreviewTable(true);
    }
}

async function loadMoreRows(dataset, limit = getRowPageSize(dataset)) {
    if (dataset === "community_analysis" && state.communityAnalysisLoading) {
        return;
    }
    if (dataset === "transformed" && state.transformedLoading) {
        return;
    }
    if (dataset === "analysis" && state.analysisLoading) {
        return;
    }
    if (!state.resultId) {
        if (dataset === "community_analysis") {
            setDatasetStatus("community_analysis", { hasMore: false });
            return;
        }
        if (dataset === "transformed") {
            setDatasetStatus("transformed", { hasMore: false });
        } else {
            setDatasetStatus("analysis", { hasMore: false });
        }
        return;
    }

    const offset = dataset === "community_analysis"
        ? state.communityAnalysisRows.length
        : dataset === "transformed"
            ? state.transformedRows.length
            : state.analysisRows.length;
    if (dataset === "community_analysis") {
        setDatasetStatus("community_analysis", { loading: true });
        updatePreviewRowStatus();
    } else if (dataset === "transformed") {
        setDatasetStatus("transformed", { loading: true });
        updatePreviewRowStatus();
    } else {
        setDatasetStatus("analysis", { loading: true });
        updatePreviewRowStatus();
    }

    try {
        const payload = await fetchRowsPage(dataset, offset, limit);

        // Append pages rather than replacing so infinite scroll keeps its already
        // rendered rows while the backend serves the next slice.
        appendRowsPayload(dataset, payload);
        updatePreviewRowStatus();
    } catch (error) {
        if (dataset === "community_analysis") {
            setDatasetStatus("community_analysis", { hasMore: false });
        } else if (dataset === "transformed") {
            setDatasetStatus("transformed", { hasMore: false });
        } else {
            setDatasetStatus("analysis", { hasMore: false });
        }
        console.error(
            `[SurveySense] Failed to load ${dataset === "community_analysis" ? "community assignment" : dataset === "analysis" ? "verbatim" : "processed"} preview rows.`,
            error,
        );
    } finally {
        if (dataset === "community_analysis") {
            setDatasetStatus("community_analysis", { loading: false });
        } else if (dataset === "transformed") {
            setDatasetStatus("transformed", { loading: false });
        } else {
            setDatasetStatus("analysis", { loading: false });
        }
        updatePreviewRowStatus();
    }
}

// Triggers infinite-scroll loading when the user is within 120 px of the bottom of the scrollable container.
function isNearBottom(element) {
    return (element.scrollTop + element.clientHeight) >= (element.scrollHeight - 120);
}
