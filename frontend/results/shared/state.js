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
 * Changes the visible workspace.
 *
 * @param {"dashboard"|"data"|"analysis"|"analysis-results"} workspace Workspace key.
 * @returns {void}
 */
export function setCurrentWorkspace(workspace) {
    state.ui.currentWorkspace = workspace || "dashboard";
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
