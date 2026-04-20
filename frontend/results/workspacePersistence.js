import { RESULT_STORAGE_KEY, elements, state } from "./shared.js";
import { closeAnalysisGroupModal } from "./modals.js";
import { closeColumnRoleModal } from "./columnRoles.js";
import { closeFilterModal } from "./workspaceFilterBar.js";
import { renderDashboard, updateWorkspaceVisibility } from "./workspaceView.js";

export async function loadResultsPage() {
    const queryHandoff = isUploadHandoffNavigation();
    if (isPageReload() && !queryHandoff) {
        sessionStorage.removeItem(RESULT_STORAGE_KEY);
        showEmptyState();
        return;
    }

    if (queryHandoff) {
        clearUploadHandoffQuery();
    }

    const payload = readStoredPayload();
    if (!payload) {
        showEmptyState();
        return;
    }

    applyPayload(payload);
}

export function resetToUploadState() {
    sessionStorage.removeItem(RESULT_STORAGE_KEY);
    resetStoredResultState();
    state.currentWorkspace = "dashboard";
    showEmptyState();
    window.dispatchEvent(new CustomEvent("verbatim:upload-reset"));
    window.scrollTo({ top: 0, behavior: "smooth" });
}

export function persistCurrentPayload() {
    if (!state.response) {
        return;
    }

    state.response.analysis_metadata_column_names = [...state.analysisMetadataColumns];
    state.response.analysis_verbatim_column_names = [...state.analysisVerbatimColumns];
    state.response.analysis_row_count = state.analysisTotalRows;
    state.response.analysis_column_names = [...state.analysisColumnNames];
    state.response.available_filters = [...state.availableFilters];
    try {
        sessionStorage.setItem(RESULT_STORAGE_KEY, JSON.stringify(state.response));
    } catch (error) {
        console.warn(
            "[Verbatim App] Failed to update the cached processed result; the current screen still works, but a later restore may be out of date.",
            error,
        );
    }
}

export function handleMissingResultState(message = "The processed result is no longer available. Upload the file again.") {
    console.warn(`[Verbatim App] Result state reset required. ${message}`);
    resetToUploadState();
}

function applyPayload(payload) {
    state.response = payload;
    state.resultId = typeof payload.result_id === "string" ? payload.result_id : null;
    applyPayloadColumns(payload);
    applyPayloadRows(payload);
    resetInteractiveWorkspaceState();
    renderResults(payload);
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
    state.transformedTotalRows = Number(payload.transformed_row_count || 0);
    state.analysisTotalRows = Number(payload.analysis_row_count || 0);
    state.transformedUnfilteredTotalRows = state.transformedTotalRows;
    state.analysisUnfilteredTotalRows = state.analysisTotalRows;
    state.transformedHasMore = state.transformedRows.length < state.transformedTotalRows;
    state.analysisHasMore = state.analysisRows.length < state.analysisTotalRows;
    state.transformedLoading = false;
    state.analysisLoading = false;
}

function resetInteractiveWorkspaceState() {
    state.selectedAnalysisColumn = state.analysisVerbatimColumns[0] || "";
    state.selectedAnalysisModel = "bertopic";
    state.analysisResult = null;
    state.analysisRunning = false;
    resetAnalysisExportState();
    resetAnalysisGroupModalState();
    state.currentWorkspace = "dashboard";
    state.showOnlyVerbatim = false;
    state.previewColumnOffset = 0;
    state.columnSearchTerm = "";
}

function readStoredPayload() {
    const raw = sessionStorage.getItem(RESULT_STORAGE_KEY);
    if (!raw) {
        return null;
    }

    try {
        const parsed = JSON.parse(raw);
        if (!isValidStoredPayload(parsed)) {
            return null;
        }
        return parsed;
    } catch {
        return null;
    }
}

function isValidStoredPayload(payload) {
    return Boolean(payload) && Array.isArray(payload.transformed_column_names);
}

function isPageReload() {
    if (typeof window === "undefined" || typeof performance === "undefined") {
        return false;
    }

    const navigationEntries = typeof performance.getEntriesByType === "function"
        ? performance.getEntriesByType("navigation")
        : [];
    const firstEntry = Array.isArray(navigationEntries) ? navigationEntries[0] : null;
    if (firstEntry && typeof firstEntry === "object" && "type" in firstEntry) {
        return firstEntry.type === "reload";
    }

    const legacyNavigation = performance.navigation;
    return Boolean(legacyNavigation && legacyNavigation.type === 1);
}

function isUploadHandoffNavigation() {
    if (typeof window === "undefined") {
        return false;
    }
    const params = new URLSearchParams(window.location.search);
    return params.get("handoff") === "1";
}

function clearUploadHandoffQuery() {
    if (typeof window === "undefined" || typeof history.replaceState !== "function") {
        return;
    }
    const params = new URLSearchParams(window.location.search);
    if (params.get("handoff") !== "1") {
        return;
    }
    params.delete("handoff");
    const query = params.toString();
    const nextUrl = `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash || ""}`;
    history.replaceState(null, "", nextUrl);
}

function resetStoredResultState() {
    state.response = null;
    state.resultId = null;
    state.analysisResult = null;
    state.analysisRows = [];
    state.transformedRows = [];
    resetAnalysisExportState();
    resetAnalysisGroupModalState();
}

function resetAnalysisExportState() {
    state.analysisExportFormat = "pdf";
    state.analysisExportMenuOpen = false;
    state.analysisExportRunning = false;
}

function resetAnalysisGroupModalState() {
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

function showEmptyState() {
    setWorkspaceBodyClasses("upload");
    closeFilterModal();
    closeColumnRoleModal();
    closeAnalysisGroupModal();
    if (elements.uploadView && elements.resultsView) {
        elements.uploadView.hidden = false;
        elements.resultsView.hidden = true;
        if (elements.uploadDataButton) {
            elements.uploadDataButton.hidden = true;
        }
        if (elements.stepPill) {
            elements.stepPill.textContent = "Step 1 of 2";
        }
        if (elements.emptyState) {
            elements.emptyState.hidden = true;
        }
    } else if (elements.emptyState) {
        elements.emptyState.hidden = false;
    }
    elements.dashboardPanel.hidden = true;
    elements.tableControls.hidden = true;
    elements.tableRowStatus.textContent = "";
    elements.tableEmpty.hidden = true;
    elements.tableWrap.hidden = true;
    elements.dataPanel.hidden = true;
    elements.analysisPanel.hidden = true;
    elements.analysisResultsPanel.hidden = true;
}

function renderResults(payload) {
    setWorkspaceBodyClasses("results");
    if (elements.emptyState) {
        elements.emptyState.hidden = true;
    }
    if (elements.uploadView) {
        elements.uploadView.hidden = true;
    }
    if (elements.resultsView) {
        elements.resultsView.hidden = false;
    }
    if (elements.uploadDataButton) {
        elements.uploadDataButton.hidden = false;
    }
    if (elements.stepPill) {
        elements.stepPill.textContent = "Step 2 of 2";
    }
    renderDashboard(payload);
    updateWorkspaceVisibility();
    closeFilterModal();
    closeColumnRoleModal();
    closeAnalysisGroupModal();
}

function setWorkspaceBodyClasses(mode) {
    document.body.classList.toggle("upload-workspace-active", mode === "upload");
    document.body.classList.toggle("dashboard-workspace-active", false);
    document.body.classList.toggle("data-workspace-active", false);
    document.body.classList.toggle("analysis-setup-workspace-active", false);
    document.body.classList.toggle("analysis-results-workspace-active", false);
}
