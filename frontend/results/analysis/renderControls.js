// Renders analysis setup controls and report export controls.
import { ANALYSIS_MODE_OPTIONS, elements, state } from "../shared.js";
import { displayColumnLabel, escapeHtml } from "../shared/utils.js";
import { displayAnalysisExportFormat, normalizeAnalysisExportFormat } from "../charts/export.js";

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
        state.selectedAnalysisModel = "community";
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
            const iconClass = option.key === "ngrams" ? "analysis-method-icon-ngrams" : "analysis-method-icon-community";
            return `
                <button
                    type="button"
                    class="analysis-method${isSelected ? " analysis-method-active" : ""}"
                    data-model-key="${escapeHtml(option.key)}"
                    aria-pressed="${isSelected ? "true" : "false"}"
                >
                    <span class="analysis-method-radio" aria-hidden="true"></span>
                    <span class="analysis-method-icon ${iconClass}" aria-hidden="true"></span>
                    <span class="analysis-method-copy-block">
                        <span class="analysis-method-title">${escapeHtml(option.label)}</span>
                        <span class="analysis-method-copy">${escapeHtml(option.description)}</span>
                    </span>
                </button>
            `;
        })
        .join("");
    elements.runAnalysisButton.disabled = state.analysisRunning || !state.selectedAnalysisColumn;
    elements.runAnalysisButton.innerHTML = state.analysisRunning
        ? '<span class="analysis-run-button-content"><span class="analysis-run-spinner" aria-hidden="true"></span><span>Running Analysis...</span></span>'
        : '<span class="analysis-run-button-content"><span class="analysis-run-icon" aria-hidden="true"></span><span>Run Analysis</span></span>';
}


export function renderAnalysisExportControls() {
    const hasReadyAnalysis = Boolean(state.resultId && state.analysisResult && state.analysisResult.ok);
    const selectedFormat = normalizeAnalysisExportFormat(state.analysisExportFormat);
    const selectedFormatLabel = displayAnalysisExportFormat(selectedFormat);
    if (!hasReadyAnalysis || state.analysisExportRunning) {
        state.analysisExportMenuOpen = false;
    }
    const isMenuOpen = hasReadyAnalysis && !state.analysisExportRunning && Boolean(state.analysisExportMenuOpen);
    if (elements.previewAnalysisReportButton) {
        elements.previewAnalysisReportButton.disabled = !hasReadyAnalysis || state.analysisExportRunning;
        elements.previewAnalysisReportButton.textContent = "Preview";
        elements.previewAnalysisReportButton.title = hasReadyAnalysis
            ? `Open a preview page for the generated ${selectedFormatLabel} report`
            : "Run an analysis to enable report preview";
    }
    if (elements.downloadAnalysisReportButton) {
        elements.downloadAnalysisReportButton.disabled = !hasReadyAnalysis || state.analysisExportRunning;
        elements.downloadAnalysisReportButton.textContent = state.analysisExportRunning
            ? "Preparing..."
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
