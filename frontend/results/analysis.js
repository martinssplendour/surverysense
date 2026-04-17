// Renders the analysis setup panel, runs NLP analysis via the API, and displays results or error states.
import { ANALYSIS_MODE_OPTIONS, RESULT_STORAGE_KEY, elements, state } from "./shared.js";
import { displayAnalysisMode, displayColumnLabel, escapeHtml, formatNumber } from "./utils.js";
import {
    clearAnalysisChart,
    renderAnalysisChart,
    renderNgramCharts,
} from "./charts.js";
import { displayAnalysisExportFormat, normalizeAnalysisExportFormat } from "./chartExport.js";
import { parseJson } from "./rows.js";

// Tracks the in-flight analysis request so it can be aborted when a new one starts.
let activeAnalysisAbortController = null;

const callbacks = {
    closeAnalysisGroupModal: () => {},
    handleMissingResultState: () => {},
    renderFilterBar: () => {},
    updateWorkspaceVisibility: () => {},
};

export function configureResultsAnalysis(nextCallbacks) {
    Object.assign(callbacks, nextCallbacks);
}

export function renderAnalysisPanel() {
    const hasVerbatimColumns = state.analysisVerbatimColumns.length > 0;
    elements.analysisPanel.hidden = !hasVerbatimColumns;
    if (!hasVerbatimColumns) {
        return;
    }

    if (!state.selectedAnalysisColumn || !state.analysisVerbatimColumns.includes(state.selectedAnalysisColumn)) {
        state.selectedAnalysisColumn = state.analysisVerbatimColumns[0] || "";
    }
    if (!ANALYSIS_MODE_OPTIONS.some((option) => option.key === state.selectedAnalysisModel)) {
        state.selectedAnalysisModel = "bertopic";
    }

    renderAnalysisControls();
}

export function renderAnalysisControls() {
    elements.analysisColumnSelect.innerHTML = state.analysisVerbatimColumns
        .map((column) => {
            const isSelected = column === state.selectedAnalysisColumn ? " selected" : "";
            return `<option value="${escapeHtml(column)}"${isSelected}>${escapeHtml(displayColumnLabel(column))}</option>`;
        })
        .join("");
    elements.analysisMethods.innerHTML = ANALYSIS_MODE_OPTIONS
        .map((option) => {
            const isSelected = option.key === state.selectedAnalysisModel;
            return `
                <button
                    type="button"
                    class="analysis-method${isSelected ? " analysis-method-active" : ""}"
                    data-model-key="${escapeHtml(option.key)}"
                    aria-pressed="${isSelected ? "true" : "false"}"
                >
                    <span class="analysis-method-title">${escapeHtml(option.label)}</span>
                    <span class="analysis-method-copy">${escapeHtml(option.description)}</span>
                </button>
            `;
        })
        .join("");
    elements.runAnalysisButton.disabled = state.analysisRunning || !state.selectedAnalysisColumn;
    elements.runAnalysisButton.innerHTML = state.analysisRunning
        ? '<span class="analysis-run-button-content"><span class="analysis-run-spinner" aria-hidden="true"></span><span>Running Analysis...</span></span>'
        : "Run Analysis";
}

export function renderAnalysisOutput() {
    renderAnalysisResultsHeader();
    callbacks.renderFilterBar();
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
    elements.analysisSummary.innerHTML = "";
    elements.analysisSummary.hidden = true;
    clearAnalysisMessage();

    if (Array.isArray(result.ngram_buckets) && result.ngram_buckets.length) {
        elements.analysisList.innerHTML = "";
        elements.analysisNgramGrid.innerHTML = "";
        renderNgramCharts(result.ngram_buckets);
        return;
    }

    const groups = Array.isArray(result.groups) ? result.groups : [];
    elements.analysisNgramGrid.innerHTML = "";
    elements.analysisList.innerHTML = groups.length
        ? ""
        : `
            <div class="analysis-item">
                <h4>No groups were returned</h4>
                <p class="analysis-sample">The analysis completed, but it did not produce any usable topics or groups for the current filtered sample.</p>
            </div>
        `;
    renderAnalysisChart(groups, Array.isArray(result.scatter_points) ? result.scatter_points : []);
}

export function renderAnalysisExportControls() {
    const hasReadyAnalysis = Boolean(state.resultId && state.analysisResult && state.analysisResult.ok);
    const selectedFormat = normalizeAnalysisExportFormat(state.analysisExportFormat);
    const selectedFormatLabel = displayAnalysisExportFormat(selectedFormat);
    if (!hasReadyAnalysis || state.analysisExportRunning) {
        state.analysisExportMenuOpen = false;
    }
    const isMenuOpen = hasReadyAnalysis && !state.analysisExportRunning && Boolean(state.analysisExportMenuOpen);
    if (elements.downloadAnalysisReportButton) {
        elements.downloadAnalysisReportButton.disabled = !hasReadyAnalysis || state.analysisExportRunning;
        elements.downloadAnalysisReportButton.textContent = state.analysisExportRunning
            ? "Preparing Report..."
            : `Download ${selectedFormatLabel}`;
        elements.downloadAnalysisReportButton.title = hasReadyAnalysis
            ? `Download report as ${selectedFormatLabel}`
            : "Run an analysis to enable report download";
    }
    if (elements.analysisExportToggleButton) {
        elements.analysisExportToggleButton.disabled = !hasReadyAnalysis || state.analysisExportRunning;
        elements.analysisExportToggleButton.setAttribute("aria-expanded", isMenuOpen ? "true" : "false");
        elements.analysisExportToggleButton.title = hasReadyAnalysis
            ? `Choose report format. Current format: ${selectedFormatLabel}`
            : "Run an analysis to choose a report format";
    }
    if (elements.analysisExportMenu) {
        elements.analysisExportMenu.hidden = !isMenuOpen;
        const items = elements.analysisExportMenu.querySelectorAll("[data-export-format]");
        items.forEach((item) => {
            if (!(item instanceof HTMLElement)) {
                return;
            }
            const itemFormat = normalizeAnalysisExportFormat(item.dataset.exportFormat);
            const isSelected = itemFormat === selectedFormat;
            item.classList.toggle("analysis-export-menu-item-selected", isSelected);
            item.setAttribute("aria-checked", isSelected ? "true" : "false");
            item.tabIndex = isMenuOpen ? 0 : -1;
        });
    }
}

export function renderAnalysisResultsHeader() {
    if (!elements.analysisResultsSubtitle) {
        return;
    }

    if (!state.analysisResult) {
        elements.analysisResultsSubtitle.textContent = "Run an analysis to see charts, distributions, and representative responses here.";
        return;
    }

    if (!state.analysisResult.ok) {
        elements.analysisResultsSubtitle.textContent = "The last analysis did not complete. Review the message below or return to the setup screen to try another method.";
        return;
    }

    const result = state.analysisResult;
    const details = [
        displayAnalysisMode(result.model_key),
        displayColumnLabel(result.text_column_name || ""),
        `${formatNumber(result.filtered_row_count || 0)} filtered rows`,
        `${formatNumber(result.valid_document_count || 0)} usable responses`,
    ];
    elements.analysisResultsSubtitle.textContent = details.join(" · ");
}

export function renderAnalysisMessage(kind, message) {
    elements.analysisMessage.hidden = false;
    elements.analysisMessage.className = `analysis-message analysis-message-${kind}`;
    elements.analysisMessage.textContent = message;
}

export function clearAnalysisMessage() {
    if (!elements.analysisMessage) {
        return;
    }
    elements.analysisMessage.hidden = true;
    elements.analysisMessage.textContent = "";
    elements.analysisMessage.className = "analysis-message";
}

export function handleAnalysisColumnChange(event) {
    const target = event.target;
    if (!(target instanceof HTMLSelectElement)) {
        return;
    }
    state.selectedAnalysisColumn = target.value;
    state.analysisResult = null;
    renderAnalysisControls();
    renderAnalysisOutput();
}

export function handleAnalysisMethodClick(event) {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
        return;
    }
    const methodButton = target.closest("[data-model-key]");
    if (!(methodButton instanceof HTMLElement)) {
        return;
    }
    const modelKey = methodButton.dataset.modelKey || "bertopic";
    if (modelKey === state.selectedAnalysisModel) {
        return;
    }
    state.selectedAnalysisModel = modelKey;
    state.analysisResult = null;
    renderAnalysisControls();
    renderAnalysisOutput();
}

export async function handleRunAnalysis() {
    await runAnalysis({ scrollIntoView: true });
}

export function getActiveAnalysisRequest() {
    return {
        textColumnName: state.analysisResult?.text_column_name || state.selectedAnalysisColumn || "",
        modelKey: state.analysisResult?.model_key || state.selectedAnalysisModel || "",
    };
}

export async function runAnalysis({
    scrollIntoView = false,
    preserveCurrentOutput = false,
    requestedColumn = "",
    requestedModel = "",
} = {}) {
    const textColumnName = requestedColumn || state.selectedAnalysisColumn || state.analysisResult?.text_column_name || "";
    const modelKey = requestedModel || state.selectedAnalysisModel || state.analysisResult?.model_key || "";
    if (!state.resultId || !textColumnName) {
        return;
    }

    callbacks.closeAnalysisGroupModal();
    state.selectedAnalysisColumn = textColumnName;
    state.selectedAnalysisModel = modelKey || state.selectedAnalysisModel;
    state.analysisRunning = true;
    renderAnalysisControls();
    if (preserveCurrentOutput && state.currentWorkspace === "analysis-results" && state.analysisResult) {
        renderAnalysisMessage("neutral", "Updating the plot for the current filters...");
    } else {
        state.analysisResult = null;
        renderAnalysisOutput();
    }

    // Cancel any in-flight request before starting a new one to avoid stale results overwriting fresh ones.
    if (activeAnalysisAbortController) {
        activeAnalysisAbortController.abort();
    }
    activeAnalysisAbortController = new AbortController();
    const signal = activeAnalysisAbortController.signal;

    try {
        const response = await fetch(`/run-analysis/${encodeURIComponent(state.resultId)}`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                model_key: modelKey,
                text_column_name: textColumnName,
                filters: state.activeFilters,
            }),
            signal,
        });
        if (response.status === 401) {
            sessionStorage.removeItem(RESULT_STORAGE_KEY);
            window.location.assign("/login");
            return;
        }
        if (response.status === 404) {
            const payload = await parseJson(response);
            callbacks.handleMissingResultState(payload.detail || "The processed result is no longer available.");
            return;
        }
        const payload = await parseJson(response);
        if (!response.ok) {
            throw new Error(payload.detail || "Unable to run analysis.");
        }

        state.analysisResult = payload;
        state.selectedAnalysisColumn = payload.text_column_name || textColumnName;
        state.selectedAnalysisModel = payload.model_key || modelKey;
        state.currentWorkspace = "analysis-results";
        callbacks.updateWorkspaceVisibility();
        renderAnalysisOutput();
        if (scrollIntoView) {
            window.scrollTo({ top: 0, behavior: "smooth" });
        }
    } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
            return;
        }
        const message = error instanceof Error ? error.message : "Unable to run analysis.";
        state.analysisResult = {
            ok: false,
            result_id: state.resultId,
            model_key: modelKey,
            model_label: displayAnalysisMode(modelKey),
            text_column_name: textColumnName,
            filtered_row_count: 0,
            valid_document_count: 0,
            skipped_document_count: 0,
            error: message,
            groups: [],
            ngram_buckets: [],
            scatter_points: [],
        };
        state.currentWorkspace = "analysis-results";
        callbacks.updateWorkspaceVisibility();
        renderAnalysisOutput();
    } finally {
        activeAnalysisAbortController = null;
        state.analysisRunning = false;
        renderAnalysisControls();
    }
}

function setAnalysisEmptyState(show) {
    if (elements.analysisEmptyState) {
        elements.analysisEmptyState.hidden = !show;
    }
}
