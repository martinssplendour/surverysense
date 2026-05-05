import { elements, setCurrentWorkspace, state } from "../shared.js";
import { closeAnalysisGroupModal } from "../modals.js";
import { closeColumnRoleModal } from "../columnRoles.js";
import { on } from "../events/bus.js";
import { closeFilterModal } from "./workspaceFilterBar.js";
import {
    clearUploadHandoffQuery,
    isPageReload,
    isUploadHandoffNavigation,
} from "./workspaceNavigationState.js";
import { applyPayloadState } from "./workspacePayloadState.js";
import { resetStoredResultState } from "./workspaceResetState.js";
import {
    clearStoredPayload,
    persistCurrentResultPayload,
    readStoredPayload,
} from "./workspaceStorage.js";
import { renderDashboard, updateWorkspaceVisibility } from "./workspaceView.js";

on("workspace:missing-result", ({ message }) => {
    handleMissingResultState(message);
});

export async function loadResultsPage() {
    const queryHandoff = isUploadHandoffNavigation();
    if (isPageReload() && !queryHandoff) {
        clearStoredPayload();
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
    void deleteServerResult(state.resultId);
    clearStoredPayload();
    resetStoredResultState();
    setCurrentWorkspace("dashboard");
    showEmptyState();
    window.dispatchEvent(new CustomEvent("verbatim:upload-reset"));
    window.scrollTo({ top: 0, behavior: "smooth" });
}

export function persistCurrentPayload() {
    persistCurrentResultPayload();
}

export function handleMissingResultState(message = "The processed result is no longer available. Upload the file again.") {
    console.warn(`[Verbatim App] Result state reset required. ${message}`);
    resetToUploadState();
}

function applyPayload(payload) {
    applyPayloadState(payload);
    renderResults(payload);
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
    if (elements.uploadView) {
        elements.uploadView.hidden = true;
    }
    if (elements.resultsView) {
        elements.resultsView.hidden = false;
    }
    if (elements.uploadDataButton) {
        elements.uploadDataButton.hidden = false;
    }
    renderDashboard(payload);
    updateWorkspaceVisibility();
    closeFilterModal();
    closeColumnRoleModal();
    closeAnalysisGroupModal();
}

async function deleteServerResult(resultId) {
    const normalizedResultId = String(resultId || "").trim();
    if (!normalizedResultId) {
        return;
    }

    try {
        await fetch(`/result/${encodeURIComponent(normalizedResultId)}`, {
            method: "DELETE",
        });
    } catch (error) {
        console.warn("[Verbatim App] Failed to delete server-side result during workspace reset.", error);
    }
}

function setWorkspaceBodyClasses(mode) {
    document.body.classList.toggle("upload-workspace-active", mode === "upload");
    document.body.classList.toggle("dashboard-workspace-active", false);
    document.body.classList.toggle("data-workspace-active", false);
    document.body.classList.toggle("analysis-setup-workspace-active", false);
    document.body.classList.toggle("analysis-results-workspace-active", false);
}
