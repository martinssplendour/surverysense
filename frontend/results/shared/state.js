import { COMMUNITY_SIMILARITY_THRESHOLD_DEFAULT } from "./constants.js";

/**
 * Central mutable state for the results page.
 *
 * New code should prefer the grouped properties and mutation helpers exported
 * here. The flat properties are kept as compatibility aliases for older modules
 * while the frontend moves away from direct mutation.
 */
const initialState = () => ({
    result: {
        response: null,
        id: null,
    },
    columns: {
        analysisMetadata: [],
        analysisVerbatim: [],
        transformed: [],
        analysis: [],
        communityAnalysis: [],
        availableFilters: [],
    },
    filters: {
        selectedColumn: "",
        selectedValue: "",
        active: {},
        showOnlyVerbatim: false,
    },
    dataset: {
        dataPreview: null,
        transformed: {
            rows: [],
            totalRows: 0,
            unfilteredTotalRows: 0,
            hasMore: false,
            loading: false,
        },
        analysis: {
            rows: [],
            totalRows: 0,
            unfilteredTotalRows: 0,
            hasMore: false,
            loading: false,
        },
        communityAnalysis: {
            rows: [],
            totalRows: 0,
            unfilteredTotalRows: 0,
            hasMore: false,
            loading: false,
        },
    },
    analysis: {
        selectedColumn: "",
        selectedModel: "community",
        communitySimilarityThreshold: COMMUNITY_SIMILARITY_THRESHOLD_DEFAULT,
        communityChartView: "bar",
        result: null,
        running: false,
        exportFormat: "pdf",
        exportMenuOpen: false,
        exportRunning: false,
    },
    dataExport: {
        menuOpen: false,
        running: false,
    },
    analysisGroupModal: {
        mode: "group",
        groupId: "",
        ngramSize: 0,
        term: "",
        sourceTerm: "",
        hitCount: 0,
        totalCount: 0,
        bucketLabel: "",
        documents: [],
        translations: {},
        translationLoading: {},
        hasMore: false,
        offset: 0,
        loading: false,
        unavailableReason: "",
    },
    ui: {
        currentWorkspace: "dashboard",
        previewColumnOffset: 0,
        columnSearchTerm: "",
    },
});

export const state = initialState();

const aliasPaths = {
    response: ["result", "response"],
    resultId: ["result", "id"],
    analysisMetadataColumns: ["columns", "analysisMetadata"],
    analysisVerbatimColumns: ["columns", "analysisVerbatim"],
    transformedColumnNames: ["columns", "transformed"],
    analysisColumnNames: ["columns", "analysis"],
    communityAnalysisColumnNames: ["columns", "communityAnalysis"],
    availableFilters: ["columns", "availableFilters"],
    selectedFilterColumn: ["filters", "selectedColumn"],
    selectedFilterValue: ["filters", "selectedValue"],
    activeFilters: ["filters", "active"],
    showOnlyVerbatim: ["filters", "showOnlyVerbatim"],
    dataPreviewDataset: ["dataset", "dataPreview"],
    transformedRows: ["dataset", "transformed", "rows"],
    analysisRows: ["dataset", "analysis", "rows"],
    communityAnalysisRows: ["dataset", "communityAnalysis", "rows"],
    transformedTotalRows: ["dataset", "transformed", "totalRows"],
    analysisTotalRows: ["dataset", "analysis", "totalRows"],
    communityAnalysisTotalRows: ["dataset", "communityAnalysis", "totalRows"],
    transformedUnfilteredTotalRows: ["dataset", "transformed", "unfilteredTotalRows"],
    analysisUnfilteredTotalRows: ["dataset", "analysis", "unfilteredTotalRows"],
    communityAnalysisUnfilteredTotalRows: ["dataset", "communityAnalysis", "unfilteredTotalRows"],
    transformedHasMore: ["dataset", "transformed", "hasMore"],
    analysisHasMore: ["dataset", "analysis", "hasMore"],
    communityAnalysisHasMore: ["dataset", "communityAnalysis", "hasMore"],
    transformedLoading: ["dataset", "transformed", "loading"],
    analysisLoading: ["dataset", "analysis", "loading"],
    communityAnalysisLoading: ["dataset", "communityAnalysis", "loading"],
    dataExportMenuOpen: ["dataExport", "menuOpen"],
    dataExportRunning: ["dataExport", "running"],
    selectedAnalysisColumn: ["analysis", "selectedColumn"],
    selectedAnalysisModel: ["analysis", "selectedModel"],
    communitySimilarityThreshold: ["analysis", "communitySimilarityThreshold"],
    communityChartView: ["analysis", "communityChartView"],
    analysisResult: ["analysis", "result"],
    analysisRunning: ["analysis", "running"],
    analysisExportFormat: ["analysis", "exportFormat"],
    analysisExportMenuOpen: ["analysis", "exportMenuOpen"],
    analysisExportRunning: ["analysis", "exportRunning"],
    analysisGroupModalMode: ["analysisGroupModal", "mode"],
    analysisGroupModalGroupId: ["analysisGroupModal", "groupId"],
    analysisGroupModalNgramSize: ["analysisGroupModal", "ngramSize"],
    analysisGroupModalTerm: ["analysisGroupModal", "term"],
    analysisGroupModalSourceTerm: ["analysisGroupModal", "sourceTerm"],
    analysisGroupModalHitCount: ["analysisGroupModal", "hitCount"],
    analysisGroupModalTotalCount: ["analysisGroupModal", "totalCount"],
    analysisGroupModalBucketLabel: ["analysisGroupModal", "bucketLabel"],
    analysisGroupModalDocuments: ["analysisGroupModal", "documents"],
    analysisGroupModalTranslations: ["analysisGroupModal", "translations"],
    analysisGroupModalTranslationLoading: ["analysisGroupModal", "translationLoading"],
    analysisGroupModalHasMore: ["analysisGroupModal", "hasMore"],
    analysisGroupModalOffset: ["analysisGroupModal", "offset"],
    analysisGroupModalLoading: ["analysisGroupModal", "loading"],
    analysisGroupModalUnavailableReason: ["analysisGroupModal", "unavailableReason"],
    currentWorkspace: ["ui", "currentWorkspace"],
    previewColumnOffset: ["ui", "previewColumnOffset"],
    columnSearchTerm: ["ui", "columnSearchTerm"],
};

Object.entries(aliasPaths).forEach(([name, path]) => {
    Object.defineProperty(state, name, {
        enumerable: true,
        configurable: false,
        get() {
            return getPath(path);
        },
        set(value) {
            setPath(path, value);
        },
    });
});

function getPath(path) {
    return path.reduce((current, key) => current[key], state);
}

function setPath(path, value) {
    const target = path.slice(0, -1).reduce((current, key) => current[key], state);
    target[path[path.length - 1]] = value;
}

function cloneArray(value) {
    return Array.isArray(value) ? [...value] : [];
}

function cloneFilterMap(value) {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
        return {};
    }
    return Object.fromEntries(
        Object.entries(value).map(([columnName, values]) => [
            columnName,
            Array.isArray(values) ? [...values] : [],
        ]),
    );
}

function datasetKey(dataset) {
    if (dataset === "community_analysis") {
        return "communityAnalysis";
    }
    return dataset === "analysis" ? "analysis" : "transformed";
}

/**
 * Resets the state object back to its default grouped values.
 *
 * @returns {void}
 */
export function resetState() {
    const nextState = initialState();
    Object.keys(nextState).forEach((key) => {
        state[key] = nextState[key];
    });
}

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
 * @param {number|string} value Threshold value from 0.4 to 1.0.
 * @returns {void}
 */
export function setCommunitySimilarityThreshold(value) {
    const threshold = Number(value);
    state.analysis.communitySimilarityThreshold = Number.isFinite(threshold)
        ? Math.min(1, Math.max(0.4, threshold))
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
 * Replaces one row dataset from an API payload.
 *
 * @param {"transformed"|"analysis"|"community_analysis"} dataset Dataset key.
 * @param {{ rows?: object[], has_more?: boolean, total_row_count?: number, unfiltered_row_count?: number, column_names?: string[] }} payload Row payload.
 * @returns {void}
 */
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

/**
 * Appends a row page to one dataset from an API payload.
 *
 * @param {"transformed"|"analysis"|"community_analysis"} dataset Dataset key.
 * @param {{ rows?: object[], has_more?: boolean, total_row_count?: number, unfiltered_row_count?: number, column_names?: string[] }} payload Row payload.
 * @returns {void}
 */
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

/**
 * Updates loading/availability flags for one row dataset.
 *
 * @param {"transformed"|"analysis"|"community_analysis"} dataset Dataset key.
 * @param {{ loading?: boolean, hasMore?: boolean }} nextState Partial row state.
 * @returns {void}
 */
export function setDatasetStatus(dataset, nextState = {}) {
    const target = state.dataset[datasetKey(dataset)];
    if ("loading" in nextState) {
        target.loading = Boolean(nextState.loading);
    }
    if ("hasMore" in nextState) {
        target.hasMore = Boolean(nextState.hasMore);
    }
}

/**
 * Clears rows and paging flags for one row dataset.
 *
 * @param {"transformed"|"analysis"|"community_analysis"} dataset Dataset key.
 * @returns {void}
 */
export function resetDatasetState(dataset) {
    const target = state.dataset[datasetKey(dataset)];
    target.rows = [];
    target.totalRows = 0;
    target.unfilteredTotalRows = 0;
    target.hasMore = false;
    target.loading = false;
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
 * Resets the analysis group drilldown modal state to defaults.
 *
 * @returns {void}
 */
export function resetAnalysisGroupModalState() {
    Object.assign(state.analysisGroupModal, initialState().analysisGroupModal);
}

/**
 * Prepares the drilldown modal for a topic/group.
 *
 * @param {object} group Analysis group payload.
 * @returns {void}
 */
export function prepareGroupModalState(group) {
    resetAnalysisGroupModalState();
    state.analysisGroupModal.mode = "group";
    state.analysisGroupModal.groupId = String(group.group_id || "");
    state.analysisGroupModal.totalCount = Number(group.count || 0);
}

/**
 * Prepares the drilldown modal for an ngram bucket item.
 *
 * @param {object} bucket Ngram bucket payload.
 * @param {object} item Ngram item payload.
 * @param {(value: unknown) => string} normalizeValue Normalizer for source terms.
 * @returns {void}
 */
export function prepareNgramModalState(bucket, item, normalizeValue = String) {
    resetAnalysisGroupModalState();
    state.analysisGroupModal.mode = "ngram";
    state.analysisGroupModal.ngramSize = Number(bucket.ngram_size || 0);
    state.analysisGroupModal.term = String(item.term || "");
    state.analysisGroupModal.sourceTerm = normalizeValue(item.source_term);
    state.analysisGroupModal.hitCount = Number(item.count || 0);
    state.analysisGroupModal.totalCount = Number(item.document_count || 0);
    state.analysisGroupModal.bucketLabel = String(bucket.label || `${bucket.ngram_size}-grams`);
}

/**
 * Updates analysis group modal loading state.
 *
 * @param {boolean} value Loading flag.
 * @returns {void}
 */
export function setAnalysisGroupModalLoading(value) {
    state.analysisGroupModal.loading = Boolean(value);
}

/**
 * Marks the drilldown documents as unavailable and clears stale page state.
 *
 * @param {string} reason User-facing reason text.
 * @returns {void}
 */
export function setAnalysisGroupModalUnavailable(reason) {
    state.analysisGroupModal.unavailableReason = String(reason || "");
    state.analysisGroupModal.documents = [];
    state.analysisGroupModal.hasMore = false;
    state.analysisGroupModal.offset = 0;
    state.analysisGroupModal.loading = false;
}

/**
 * Applies a page of analysis group/phrase documents to the modal.
 *
 * @param {{ documents?: object[], offset?: number, has_more?: boolean, total_count?: number, hit_count?: number }} payload Document payload.
 * @param {{ reset?: boolean, fallbackTotalCount?: number }} options Apply options.
 * @returns {void}
 */
export function applyAnalysisGroupDocumentsPayload(payload = {}, { reset = false, fallbackTotalCount = 0 } = {}) {
    const documents = cloneArray(payload.documents);
    state.analysisGroupModal.unavailableReason = "";
    state.analysisGroupModal.documents = reset
        ? documents
        : state.analysisGroupModal.documents.concat(documents);
    state.analysisGroupModal.offset = Number(payload.offset || 0) + documents.length;
    state.analysisGroupModal.hasMore = Boolean(payload.has_more);
    state.analysisGroupModal.totalCount = Number(
        payload.total_count || state.analysisGroupModal.totalCount || fallbackTotalCount || 0,
    );
    if ("hit_count" in payload) {
        state.analysisGroupModal.hitCount = Number(payload.hit_count || state.analysisGroupModal.hitCount || 0);
    }
}

/**
 * Marks one drilldown document translation as loading or finished.
 *
 * @param {string} documentKey Document key.
 * @param {boolean} value Loading flag.
 * @returns {void}
 */
export function setAnalysisDocumentTranslationLoading(documentKey, value) {
    const nextLoading = { ...state.analysisGroupModal.translationLoading };
    if (value) {
        nextLoading[documentKey] = true;
    } else {
        delete nextLoading[documentKey];
    }
    state.analysisGroupModal.translationLoading = nextLoading;
}

/**
 * Stores one translated drilldown document.
 *
 * @param {string} documentKey Document key.
 * @param {{ text?: string, translated?: boolean, warning?: string }} translation Translation payload.
 * @returns {void}
 */
export function setAnalysisDocumentTranslation(documentKey, translation) {
    state.analysisGroupModal.translations = {
        ...state.analysisGroupModal.translations,
        [documentKey]: {
            text: String(translation.text || ""),
            translated: Boolean(translation.translated),
            warning: translation.warning ? String(translation.warning) : "",
        },
    };
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
