// Renders the active analysis result body and message state.
import { elements, state } from "../shared.js";
import { escapeHtml } from "../shared/utils.js";
import {
    clearAnalysisChart,
    renderAnalysisChart,
    renderNgramCharts,
} from "../charts.js";
import { renderFilterBar } from "../workspace/workspaceFilterBar.js";
import { renderAnalysisExportControls } from "./renderControls.js";
import { renderAnalysisInsightSummary } from "./renderInsightSummary.js";
import { renderAnalysisResultsHeader } from "./renderResultsHeader.js";

export function renderAnalysisOutput() {
    renderAnalysisResultsHeader();
    renderFilterBar();
    renderAnalysisExportControls();

    if (!state.analysisResult) {
        elements.analysisSummary.innerHTML = "";
        elements.analysisSummary.hidden = true;
        clearAnalysisChart();
        elements.analysisList.innerHTML = "";
        elements.analysisNgramGrid.innerHTML = "";
        clearAnalysisMessage();
        setAnalysisEmptyState(true);
        return;
    }

    const result = state.analysisResult;
    if (!result.ok) {
        setAnalysisEmptyState(false);
        elements.analysisSummary.innerHTML = "";
        elements.analysisSummary.hidden = true;
        clearAnalysisChart();
        elements.analysisList.innerHTML = `
            <div class="analysis-item">
                <h4>Analysis could not run</h4>
                <p class="analysis-sample">${escapeHtml(result.error || "The selected analysis failed.")}</p>
            </div>
        `;
        elements.analysisNgramGrid.innerHTML = "";
        renderAnalysisMessage("error", result.error || "The selected analysis failed.");
        return;
    }

    setAnalysisEmptyState(false);
    renderAnalysisInsightSummary(result);
    clearAnalysisMessage();

    if (Array.isArray(result.ngram_buckets) && result.ngram_buckets.length) {
        elements.analysisList.innerHTML = "";
        elements.analysisNgramGrid.innerHTML = "";
        renderNgramCharts(result.ngram_buckets);
        return;
    }

    const groups = Array.isArray(result.groups) ? result.groups : [];
    const assignedGroups = groups.filter((group) => !group?.is_noise);
    elements.analysisNgramGrid.innerHTML = "";
    elements.analysisList.innerHTML = assignedGroups.length
        ? ""
        : `
            <div class="analysis-item">
                <h4>No groups were returned</h4>
                <p class="analysis-sample">The analysis completed, but it did not produce any usable topics or groups for the current filtered sample.</p>
            </div>
        `;
    renderAnalysisChart(
        assignedGroups,
        Array.isArray(result.scatter_points) ? result.scatter_points : [],
        Array.isArray(result.network_edges) ? result.network_edges : [],
    );
}





export function renderAnalysisMessage(kind, message) {
    elements.analysisMessage.hidden = false;
    elements.analysisMessage.className = `analysis-message analysis-message-${kind}`;
    elements.analysisMessage.textContent = message;
}


export function renderAnalysisRetryMessage(message) {
    elements.analysisMessage.hidden = false;
    elements.analysisMessage.className = "analysis-message analysis-message-warning analysis-message-loading";
    elements.analysisMessage.innerHTML = `
        <span class="analysis-message-spinner" aria-hidden="true"></span>
        <span>${escapeHtml(message)}</span>
    `;
}


export function clearAnalysisMessage() {
    if (!elements.analysisMessage) {
        return;
    }
    elements.analysisMessage.hidden = true;
    elements.analysisMessage.textContent = "";
    elements.analysisMessage.innerHTML = "";
    elements.analysisMessage.className = "analysis-message";
}


function setAnalysisEmptyState(show) {
    if (elements.analysisEmptyState) {
        elements.analysisEmptyState.hidden = !show;
    }
}
