import {
    COMMUNITY_SIMILARITY_THRESHOLD_DEFAULT,
    COMMUNITY_SIMILARITY_THRESHOLD_MAX,
    COMMUNITY_SIMILARITY_THRESHOLD_MIN,
} from "./constants.js";
import { applyDatasetPayload, appendDatasetPayload, resetDatasetState, setDatasetStatus } from "./stateDataset.js";
import {
    applyAnalysisGroupDocumentsPayload,
    prepareGroupModalState,
    prepareNgramModalState,
    resetAnalysisGroupModalState,
    setAnalysisDocumentTranslation,
    setAnalysisDocumentTranslationLoading,
    setAnalysisGroupModalLoading,
    setAnalysisGroupModalUnavailable,
} from "./stateModal.js";
import { cloneArray, cloneFilterMap, resetState, state } from "./stateCore.js";

export { resetState, state } from "./stateCore.js";
export { applyDatasetPayload, appendDatasetPayload, resetDatasetState, setDatasetStatus } from "./stateDataset.js";
export {
    applyAnalysisGroupDocumentsPayload,
    prepareGroupModalState,
    prepareNgramModalState,
    resetAnalysisGroupModalState,
    setAnalysisDocumentTranslation,
    setAnalysisDocumentTranslationLoading,
    setAnalysisGroupModalLoading,
    setAnalysisGroupModalUnavailable,
} from "./stateModal.js";

/**
 * Central mutable state for the results page.
 *
 * New code should prefer the grouped properties and mutation helpers exported
 * here. The flat properties are kept as compatibility aliases for older modules
 * while the frontend moves away from direct mutation.
 */
/**
 * Stores the active result payload and server-side result ID.
 *
 * @param {object|null} response Raw upload/result payload.
 * @param {string|null} resultId Server-side result identifier.
 * @returns {void}
 */
export function setResultIdentity(response, resultId) {
    state.result.response = response;
    state.result.id = typeof resultId === "string" ? resultId : null;
}

/**
 * Replaces the active metadata filter map.
 *
 * @param {Record<string, string[]>} filters Next active filters by column name.
 * @returns {void}
 */
export function setActiveFilters(filters) {
    state.filters.active = cloneFilterMap(filters);
}

/**
 * Updates the selected filter controls.
 *
 * @param {{ column?: string, value?: string }} selection Selected filter column and value.
 * @returns {void}
 */
export function setSelectedFilter(selection) {
    state.filters.selectedColumn = String(selection.column || "");
    state.filters.selectedValue = String(selection.value || "");
}

/**
 * Updates the selected analysis column and model.
 *
 * @param {{ column?: string, model?: string }} selection Selected analysis controls.
 * @returns {void}
 */
export function setAnalysisSelection(selection) {
    state.analysis.selectedColumn = String(selection.column || "");
    state.analysis.selectedModel = String(selection.model || state.analysis.selectedModel || "community");
}

/**
 * Updates only the selected analysis column.
 *
 * @param {string} column Selected analysis column.
 * @returns {void}
 */
export function setSelectedAnalysisColumn(column) {
    state.analysis.selectedColumn = String(column || "");
}

/**
 * Updates only the selected analysis model.
 *
 * @param {string} model Selected analysis model.
 * @returns {void}
 */
export function setSelectedAnalysisModel(model) {
    state.analysis.selectedModel = String(model || state.analysis.selectedModel || "community");
}

/**
 * Updates the selected community cosine similarity threshold.
 *
 * @param {number|string} value Threshold value from 0.6 to 1.0.
 * @returns {void}
 */
export function setCommunitySimilarityThreshold(value) {
    const threshold = Number(value);
    state.analysis.communitySimilarityThreshold = Number.isFinite(threshold)
        ? Math.min(COMMUNITY_SIMILARITY_THRESHOLD_MAX, Math.max(COMMUNITY_SIMILARITY_THRESHOLD_MIN, threshold))
        : COMMUNITY_SIMILARITY_THRESHOLD_DEFAULT;
}

/**
 * Marks whether an analysis request is currently running.
 *
 * @param {boolean} value Running flag.
 * @returns {void}
 */
export function setAnalysisRunning(value) {
    state.analysis.running = Boolean(value);
}

/**
 * Stores the latest analysis result payload.
 *
 * @param {object|null} result Analysis response payload.
 * @returns {void}
 */
export function setAnalysisResult(result) {
    state.analysis.result = result || null;
}

/**
 * Updates community analysis chart display mode.
 *
 * @param {"bar"|"network"} view Chart view key.
 * @returns {void}
 */
export function setCommunityChartView(view) {
    state.analysis.communityChartView = view === "network" ? "network" : "bar";
}

/**
 * Updates analysis report export controls.
 *
 * @param {{ format?: string, menuOpen?: boolean, running?: boolean }} nextState Partial export state.
 * @returns {void}
 */
export function setAnalysisExportState(nextState = {}) {
    if ("format" in nextState) {
        state.analysis.exportFormat = String(nextState.format || "pdf");
    }
    if ("menuOpen" in nextState) {
        state.analysis.exportMenuOpen = Boolean(nextState.menuOpen);
    }
    if ("running" in nextState) {
        state.analysis.exportRunning = Boolean(nextState.running);
    }
}

/**
 * Updates cleaned-data export controls.
 *
 * @param {{ menuOpen?: boolean, running?: boolean }} nextState Partial export state.
 * @returns {void}
 */
export function setDataExportState(nextState = {}) {
    if ("menuOpen" in nextState) {
        state.dataExport.menuOpen = Boolean(nextState.menuOpen);
    }
    if ("running" in nextState) {
        state.dataExport.running = Boolean(nextState.running);
    }
}

/**
 * Changes the visible workspace.
 *
 * @param {"dashboard"|"data"|"analysis"|"analysis-results"} workspace Workspace key.
 * @returns {void}
 */
export function setCurrentWorkspace(workspace) {
    state.ui.currentWorkspace = workspace || "dashboard";
}

/**
 * Updates the data table preview controls.
 *
 * @param {{ dataset?: string|null, showOnlyVerbatim?: boolean, columnOffset?: number, columnSearchTerm?: string }} nextState Partial preview state.
 * @returns {void}
 */
export function setPreviewState(nextState = {}) {
    if ("dataset" in nextState) {
        state.dataset.dataPreview = nextState.dataset || null;
    }
    if ("showOnlyVerbatim" in nextState) {
        state.filters.showOnlyVerbatim = Boolean(nextState.showOnlyVerbatim);
    }
    if ("columnOffset" in nextState) {
        state.ui.previewColumnOffset = Number(nextState.columnOffset || 0);
    }
    if ("columnSearchTerm" in nextState) {
        state.ui.columnSearchTerm = String(nextState.columnSearchTerm || "");
    }
}

/**
 * Applies a newly loaded result payload and resets interactive UI state.
 *
 * @param {object} payload Upload/result payload.
 * @returns {void}
 */
export function applyResultPayload(payload) {
    setResultIdentity(payload, typeof payload.result_id === "string" ? payload.result_id : null);
    state.columns.analysisMetadata = cloneArray(payload.analysis_metadata_column_names);
    state.columns.analysisVerbatim = cloneArray(payload.analysis_verbatim_column_names);
    state.columns.transformed = cloneArray(payload.transformed_column_names);
    state.columns.analysis = cloneArray(payload.analysis_column_names);
    state.columns.communityAnalysis = [];
    state.columns.availableFilters = cloneArray(payload.available_filters);
    state.filters.selectedColumn = "";
    state.filters.selectedValue = "";
    state.filters.active = {};
    state.filters.showOnlyVerbatim = false;
    state.dataset.dataPreview = null;
    state.dataset.transformed = {
        rows: cloneArray(payload.transformed_preview_rows),
        totalRows: Number(payload.transformed_row_count || 0),
        unfilteredTotalRows: Number(payload.transformed_row_count || 0),
        hasMore: cloneArray(payload.transformed_preview_rows).length < Number(payload.transformed_row_count || 0),
        loading: false,
    };
    state.dataset.analysis = {
        rows: cloneArray(payload.analysis_preview_rows),
        totalRows: Number(payload.analysis_row_count || 0),
        unfilteredTotalRows: Number(payload.analysis_row_count || 0),
        hasMore: cloneArray(payload.analysis_preview_rows).length < Number(payload.analysis_row_count || 0),
        loading: false,
    };
    state.dataset.communityAnalysis = {
        rows: [],
        totalRows: 0,
        unfilteredTotalRows: 0,
        hasMore: false,
        loading: false,
    };
    state.analysis.selectedColumn = state.columns.analysisVerbatim[0] || "";
    state.analysis.selectedModel = "community";
    state.analysis.communitySimilarityThreshold = COMMUNITY_SIMILARITY_THRESHOLD_DEFAULT;
    state.analysis.communityChartView = "bar";
    state.analysis.result = null;
    state.analysis.running = false;
    state.analysis.exportFormat = "pdf";
    state.analysis.exportMenuOpen = false;
    state.analysis.exportRunning = false;
    state.dataExport.menuOpen = false;
    state.dataExport.running = false;
    resetAnalysisGroupModalState();
    state.ui.currentWorkspace = "dashboard";
    state.ui.previewColumnOffset = 0;
    state.ui.columnSearchTerm = "";
}

/**
 * Clears stored result-specific state while leaving the page in its default workspace.
 *
 * @returns {void}
 */
export function resetStoredResultState() {
    state.result.response = null;
    state.result.id = null;
    state.analysis.result = null;
    state.analysis.communityChartView = "bar";
    state.dataset.analysis.rows = [];
    state.dataset.transformed.rows = [];
    state.dataset.communityAnalysis.rows = [];
    state.columns.communityAnalysis = [];
    resetAnalysisExportState();
    resetDataExportState();
    resetAnalysisGroupModalState();
}

/**
 * Resets report export controls to defaults.
 *
 * @returns {void}
 */
export function resetAnalysisExportState() {
    state.analysis.exportFormat = "pdf";
    state.analysis.exportMenuOpen = false;
    state.analysis.exportRunning = false;
}

/**
 * Resets cleaned-data export controls to defaults.
 *
 * @returns {void}
 */
export function resetDataExportState() {
    state.dataExport.menuOpen = false;
    state.dataExport.running = false;
}

/**
 * Applies updated column roles and clears derived analysis state.
 *
 * @param {object} payload Column-role API payload.
 * @returns {void}
 */
export function applyColumnRolePayload(payload) {
    state.columns.analysisMetadata = cloneArray(payload.analysis_metadata_column_names);
    state.columns.analysisVerbatim = cloneArray(payload.analysis_verbatim_column_names);
    state.columns.analysis = cloneArray(payload.analysis_column_names);
    state.dataset.analysis.totalRows = Number(payload.analysis_row_count || 0);
    state.columns.availableFilters = cloneArray(payload.available_filters);
    if (!state.columns.analysisVerbatim.includes(state.analysis.selectedColumn)) {
        state.analysis.selectedColumn = state.columns.analysisVerbatim[0] || "";
    }
    state.analysis.result = null;
    state.dataset.dataPreview = null;
    state.columns.communityAnalysis = [];
}

/**
 * Updates the cached response payload with the current derived column metadata.
 *
 * @returns {object|null} Updated response payload.
 */
export function syncResultResponseMetadata() {
    if (!state.result.response) {
        return null;
    }
    state.result.response = {
        ...state.result.response,
        analysis_metadata_column_names: [...state.columns.analysisMetadata],
        analysis_verbatim_column_names: [...state.columns.analysisVerbatim],
        analysis_row_count: state.dataset.analysis.totalRows,
        analysis_column_names: [...state.columns.analysis],
        available_filters: [...state.columns.availableFilters],
    };
    return state.result.response;
}

/**
 * Invalidates row datasets after a new analysis result.
 *
 * @returns {void}
 */
export function invalidateRowDatasetsAfterAnalysis() {
    resetDatasetState("transformed");
    resetDatasetState("analysis");
    resetDatasetState("community_analysis");
    state.columns.communityAnalysis = [];
    state.dataset.dataPreview = null;
    state.dataset.transformed.hasMore = Boolean(state.result.id);
    state.dataset.analysis.hasMore = Boolean(state.result.id);
    state.dataset.communityAnalysis.hasMore = Boolean(
        state.analysis.result?.model_key && state.analysis.result?.model_key !== "ngrams",
    );
}
