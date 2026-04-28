import { elements, state } from "../shared.js";
import { clearDataExportMessage, renderDataExportControls } from "../dataExport.js";
import { on } from "../events/bus.js";
import { formatNumber, summaryMetric } from "../shared/utils.js";
import {
    currentPreviewDataset,
    ensureDatasetRowCount,
    getInitialVisibleRowTarget,
} from "../data/rows.js";
import { renderAnalysisOutput, renderAnalysisPanel } from "../analysis.js";
import { closeAnalysisGroupModal } from "../modals.js";
import { renderFilterBar } from "./workspaceFilterBar.js";
import { renderPreviewTable, syncSliderRange } from "./workspacePreviewTable.js";

on("workspace:visibility:update", () => {
    updateWorkspaceVisibility();
});

export function renderDashboard(payload) {
    const filename = typeof payload.filename === "string" && payload.filename.trim()
        ? payload.filename.trim()
        : "upload.csv";
    const rowCount = Number(payload.transformed_row_count || 0);
    const columnCount = Array.isArray(payload.transformed_column_names) ? payload.transformed_column_names.length : 0;
    const verbatimCount = state.analysisVerbatimColumns.length;

    elements.dashboardFileName.textContent = filename;

    const metrics = [
        summaryMetric("rows", "Rows", formatNumber(rowCount)),
        summaryMetric("columns", "Columns", formatNumber(columnCount)),
        summaryMetric("verbatim", "Verbatim Columns", formatNumber(verbatimCount)),
    ];
    elements.dashboardMetrics.innerHTML = metrics.join("");
    elements.openAnalysisButton.disabled = !verbatimCount;
    elements.openDataButton.disabled = !verbatimCount;
    if (elements.dashboardActionNote) {
        elements.dashboardActionNote.hidden = Boolean(verbatimCount);
        elements.dashboardActionNote.textContent = verbatimCount
            ? ""
            : "No verbatim columns detected - use Edit Columns to assign them.";
    }
}

export async function openWorkspace(nextWorkspace) {
    closeAnalysisGroupModal();
    if (nextWorkspace !== "data") {
        state.dataExportMenuOpen = false;
        state.dataPreviewDataset = null;
    }
    state.currentWorkspace = nextWorkspace;
    updateWorkspaceVisibility();

    if (nextWorkspace === "data") {
        clearDataExportMessage();
        renderDataExportControls();
        renderFilterBar();
        const dataset = currentPreviewDataset();
        await ensureDatasetRowCount(dataset, getInitialVisibleRowTarget(dataset));
        renderPreviewTable(false);
        syncSliderRange();
    } else if (nextWorkspace === "analysis") {
        renderAnalysisPanel();
    } else if (nextWorkspace === "analysis-results") {
        renderAnalysisOutput();
    }
}

export function updateWorkspaceVisibility() {
    elements.dashboardPanel.hidden = state.currentWorkspace !== "dashboard";
    elements.dataPanel.hidden = state.currentWorkspace !== "data";
    elements.analysisPanel.hidden = state.currentWorkspace !== "analysis" || !state.analysisVerbatimColumns.length;
    elements.analysisResultsPanel.hidden = state.currentWorkspace !== "analysis-results";
    document.body.classList.toggle("dashboard-workspace-active", state.currentWorkspace === "dashboard");
    document.body.classList.toggle("data-workspace-active", state.currentWorkspace === "data");
    document.body.classList.toggle("analysis-setup-workspace-active", state.currentWorkspace === "analysis");
    document.body.classList.toggle("analysis-results-workspace-active", state.currentWorkspace === "analysis-results");
}
