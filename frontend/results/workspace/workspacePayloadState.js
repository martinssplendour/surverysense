import { state } from "../shared.js";
import {
    resetAnalysisExportState,
    resetAnalysisGroupModalState,
} from "./workspaceResetState.js";


export function applyPayloadState(payload) {
    state.response = payload;
    state.resultId = typeof payload.result_id === "string" ? payload.result_id : null;
    applyPayloadColumns(payload);
    applyPayloadRows(payload);
    resetInteractiveWorkspaceState();
}


function applyPayloadColumns(payload) {
    state.analysisMetadataColumns = Array.isArray(payload.analysis_metadata_column_names)
        ? payload.analysis_metadata_column_names
        : [];
    state.analysisVerbatimColumns = Array.isArray(payload.analysis_verbatim_column_names)
        ? payload.analysis_verbatim_column_names
        : [];
    state.transformedColumnNames = Array.isArray(payload.transformed_column_names)
        ? payload.transformed_column_names
        : [];
    state.analysisColumnNames = Array.isArray(payload.analysis_column_names)
        ? payload.analysis_column_names
        : [];
    state.communityAnalysisColumnNames = [];
    state.availableFilters = Array.isArray(payload.available_filters)
        ? payload.available_filters
        : [];
}


function applyPayloadRows(payload) {
    state.selectedFilterColumn = "";
    state.selectedFilterValue = "";
    state.activeFilters = {};
    state.transformedRows = Array.isArray(payload.transformed_preview_rows)
        ? [...payload.transformed_preview_rows]
        : [];
    state.analysisRows = Array.isArray(payload.analysis_preview_rows)
        ? [...payload.analysis_preview_rows]
        : [];
    state.communityAnalysisRows = [];
    state.transformedTotalRows = Number(payload.transformed_row_count || 0);
    state.analysisTotalRows = Number(payload.analysis_row_count || 0);
    state.communityAnalysisTotalRows = 0;
    state.transformedUnfilteredTotalRows = state.transformedTotalRows;
    state.analysisUnfilteredTotalRows = state.analysisTotalRows;
    state.communityAnalysisUnfilteredTotalRows = 0;
    state.transformedHasMore = state.transformedRows.length < state.transformedTotalRows;
    state.analysisHasMore = state.analysisRows.length < state.analysisTotalRows;
    state.communityAnalysisHasMore = false;
    state.transformedLoading = false;
    state.analysisLoading = false;
    state.communityAnalysisLoading = false;
}


function resetInteractiveWorkspaceState() {
    state.selectedAnalysisColumn = state.analysisVerbatimColumns[0] || "";
    state.selectedAnalysisModel = "community";
    state.communityChartView = "bar";
    state.analysisResult = null;
    state.analysisRunning = false;
    resetAnalysisExportState();
    resetAnalysisGroupModalState();
    state.currentWorkspace = "dashboard";
    state.showOnlyVerbatim = false;
    state.dataPreviewDataset = null;
    state.previewColumnOffset = 0;
    state.columnSearchTerm = "";
}
