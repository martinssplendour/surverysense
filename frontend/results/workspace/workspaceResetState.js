import { state } from "../shared.js";


export function resetStoredResultState() {
    state.response = null;
    state.resultId = null;
    state.analysisResult = null;
    state.communityChartView = "bar";
    state.analysisRows = [];
    state.transformedRows = [];
    state.communityAnalysisRows = [];
    state.communityAnalysisColumnNames = [];
    resetDataExportState();
    resetAnalysisExportState();
    resetAnalysisGroupModalState();
}


export function resetAnalysisExportState() {
    state.analysisExportFormat = "pdf";
    state.analysisExportMenuOpen = false;
    state.analysisExportRunning = false;
}


export function resetDataExportState() {
    state.dataExportMenuOpen = false;
    state.dataExportRunning = false;
}


export function resetAnalysisGroupModalState() {
    state.analysisGroupModalMode = "group";
    state.analysisGroupModalGroupId = "";
    state.analysisGroupModalNgramSize = 0;
    state.analysisGroupModalTerm = "";
    state.analysisGroupModalSourceTerm = "";
    state.analysisGroupModalHitCount = 0;
    state.analysisGroupModalTotalCount = 0;
    state.analysisGroupModalBucketLabel = "";
    state.analysisGroupModalDocuments = [];
    state.analysisGroupModalTranslations = {};
    state.analysisGroupModalTranslationLoading = {};
    state.analysisGroupModalHasMore = false;
    state.analysisGroupModalOffset = 0;
    state.analysisGroupModalLoading = false;
}
