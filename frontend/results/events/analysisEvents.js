import { elements, state } from "../shared.js";
import { downloadAnalysisReport, normalizeAnalysisExportFormat, previewAnalysisReport } from "../charts/export.js";
import {
    handleAnalysisColumnChange,
    handleAnalysisMethodClick,
    handleRunAnalysis,
    renderAnalysisExportControls,
} from "../analysis.js";
import { resizeAnalysisPlots } from "../charts.js";

export function bindAnalysisEvents() {
    normalizeAnalysisResultsActionLayout();
    elements.downloadAnalysisReportButton?.addEventListener("click", () => {
        void downloadAnalysisReport();
    });
    elements.previewAnalysisReportButton?.addEventListener("click", () => {
        void previewAnalysisReport();
    });
    elements.analysisExportToggleButton?.addEventListener("click", handleExportToggleClick);
    elements.analysisExportMenu?.addEventListener("click", handleExportMenuClick);
    elements.analysisColumnSelect?.addEventListener("change", handleAnalysisColumnChange);
    elements.analysisMethods?.addEventListener("click", handleAnalysisMethodClick);
    elements.runAnalysisButton?.addEventListener("click", handleRunAnalysis);
    document.addEventListener("click", handleAnalysisExportDocumentClick);
    window.addEventListener("resize", resizeAnalysisPlots);
}

function normalizeAnalysisResultsActionLayout() {
    const exportSplit = document.querySelector(".analysis-export-split");
    const filterRow = document.querySelector("#analysis-results-filter-bar .filter-chip-row");

    if (filterRow instanceof HTMLElement) {
        filterRow.classList.add("analysis-results-filter-row");
    }

    if (exportSplit instanceof HTMLElement) {
        if (!(elements.previewAnalysisReportButton instanceof HTMLButtonElement)) {
            elements.previewAnalysisReportButton = document.createElement("button");
            elements.previewAnalysisReportButton.type = "button";
            elements.previewAnalysisReportButton.id = "preview-analysis-report-btn";
        }

        if (elements.previewAnalysisReportButton instanceof HTMLButtonElement) {
            elements.previewAnalysisReportButton.className = "button button-primary analysis-export-preview-button";
            elements.previewAnalysisReportButton.textContent = "Preview";
            if (elements.previewAnalysisReportButton.parentElement !== exportSplit) {
                const downloadButton = elements.downloadAnalysisReportButton;
                const referenceNode = downloadButton instanceof Node && exportSplit.contains(downloadButton)
                    ? downloadButton
                    : exportSplit.firstChild;
                exportSplit.insertBefore(elements.previewAnalysisReportButton, referenceNode);
            }
        }

        if (elements.downloadAnalysisReportButton instanceof HTMLButtonElement) {
            elements.downloadAnalysisReportButton.className = "button button-primary analysis-export-main-button";
            if (elements.downloadAnalysisReportButton.parentElement !== exportSplit) {
                const toggleButton = elements.analysisExportToggleButton;
                const referenceNode = toggleButton instanceof Node && exportSplit.contains(toggleButton)
                    ? toggleButton
                    : null;
                exportSplit.insertBefore(elements.downloadAnalysisReportButton, referenceNode);
            }
        }

        if (elements.analysisExportToggleButton instanceof HTMLButtonElement) {
            elements.analysisExportToggleButton.className = "button button-primary analysis-export-toggle-button";
            if (elements.analysisExportToggleButton.parentElement !== exportSplit) {
                exportSplit.appendChild(elements.analysisExportToggleButton);
            }
        }

        if (elements.analysisExportMenu instanceof HTMLElement && elements.analysisExportMenu.parentElement !== exportSplit) {
            exportSplit.appendChild(elements.analysisExportMenu);
        }
    }

    if (elements.analysisViewDataButton instanceof HTMLButtonElement && filterRow instanceof HTMLElement) {
        elements.analysisViewDataButton.className = "dashboard-data-link analysis-results-data-link";
        elements.analysisViewDataButton.innerHTML = 'View data <span aria-hidden="true">&rarr;</span>';
        if (elements.analysisViewDataButton.parentElement !== filterRow) {
            filterRow.appendChild(elements.analysisViewDataButton);
        }
    }
}

function handleExportToggleClick(event) {
    event.stopPropagation();
    if (state.analysisExportRunning) {
        return;
    }
    state.analysisExportMenuOpen = !state.analysisExportMenuOpen;
    renderAnalysisExportControls();
}

function handleExportMenuClick(event) {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
        return;
    }
    const formatButton = target.closest("[data-export-format]");
    if (!(formatButton instanceof HTMLElement)) {
        return;
    }
    state.analysisExportFormat = normalizeAnalysisExportFormat(formatButton.dataset.exportFormat);
    state.analysisExportMenuOpen = false;
    renderAnalysisExportControls();
}

function handleAnalysisExportDocumentClick(event) {
    const target = event.target;
    if (!(target instanceof Node) || !state.analysisExportMenuOpen) {
        return;
    }
    if (!(elements.analysisExportMenu?.contains(target) || elements.analysisExportToggleButton?.contains(target))) {
        state.analysisExportMenuOpen = false;
        renderAnalysisExportControls();
    }
}
