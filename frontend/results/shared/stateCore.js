import {
    COMMUNITY_SIMILARITY_THRESHOLD_DEFAULT,
} from "./constants.js";

export const initialState = () => ({
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

export function cloneArray(value) {
    return Array.isArray(value) ? [...value] : [];
}

export function cloneFilterMap(value) {
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

export function datasetKey(dataset) {
    if (dataset === "community_analysis") {
        return "communityAnalysis";
    }
    return dataset === "analysis" ? "analysis" : "transformed";
}

export function resetState() {
    const nextState = initialState();
    Object.keys(nextState).forEach((key) => {
        state[key] = nextState[key];
    });
}
