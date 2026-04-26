import { elements, state } from "./shared.js";
import { downloadAnalysisReport, normalizeAnalysisExportFormat, previewAnalysisReport } from "./charts/export.js";
import { downloadDataExport, renderDataExportControls } from "./dataExport.js";
import {
    closeAnalysisGroupModal,
    loadAnalysisGroupDocuments,
    loadAnalysisNgramDocuments,
    translateAnalysisDocument,
} from "./modals.js";
import {
    applyColumnRoleChange,
    closeColumnRoleModal,
    handleColumnRoleSearch,
    openColumnRoleModal,
    renderColumnRoleSelectionState,
} from "./columnRoles.js";
import {
    handleAddFilter,
    handleClearFilters,
    handleFilterColumnChange,
    handleFilterValueChange,
    removeActiveFilter,
} from "./filters.js";
import {
    handleAnalysisColumnChange,
    handleAnalysisMethodClick,
    handleRunAnalysis,
    renderAnalysisExportControls,
} from "./analysis.js";
import {
    closeFilterModal,
    handleDocumentKeydown,
    handlePreviewModeChange,
    handlePreviewTableScroll,
    handleSliderInput,
    openFilterModal,
    openWorkspace,
    resetToUploadState,
    syncSliderRange,
} from "./workspace/workspace.js";
import { resizeAnalysisPlots } from "./charts.js";


export function bindResultsEvents() {
    normalizeAnalysisResultsActionLayout();
    elements.uploadDataButton?.addEventListener("click", resetToUploadState);
    elements.openAnalysisButton?.addEventListener("click", () => {
        void openWorkspace("analysis");
    });
    elements.openDataButton?.addEventListener("click", () => {
        state.dataPreviewDataset = null;
        state.showOnlyVerbatim = false;
        void openWorkspace("data");
    });
    elements.dataExportToggleButton?.addEventListener("click", handleDataExportToggleClick);
    elements.dataExportMenu?.addEventListener("click", handleDataExportMenuClick);
    elements.dataAnalyseButton?.addEventListener("click", () => {
        void openWorkspace("analysis");
    });
    elements.backToAnalysisResultsDataButton?.addEventListener("click", () => {
        void openWorkspace("analysis-results");
    });
    elements.openFilterModalButton?.addEventListener("click", openFilterModal);
    elements.openAnalysisResultsFilterModalButton?.addEventListener("click", openFilterModal);
    elements.editColumnsButton?.addEventListener("click", openColumnRoleModal);
    elements.backToDashboardAnalysisButton?.addEventListener("click", () => {
        void openWorkspace("dashboard");
    });
    elements.backToAnalysisSetupButton?.addEventListener("click", () => {
        void openWorkspace("analysis");
    });
    elements.analysisViewDataButton?.addEventListener("click", () => {
        state.dataPreviewDataset = state.analysisResult?.model_key && state.analysisResult?.model_key !== "ngrams"
            ? "community_analysis"
            : null;
        state.showOnlyVerbatim = false;
        void openWorkspace("data");
    });
    elements.backToDashboardResultsButton?.addEventListener("click", () => {
        void openWorkspace("dashboard");
    });
    elements.downloadAnalysisReportButton?.addEventListener("click", () => {
        void downloadAnalysisReport();
    });
    elements.previewAnalysisReportButton?.addEventListener("click", () => {
        void previewAnalysisReport();
    });
    elements.analysisExportToggleButton?.addEventListener("click", handleExportToggleClick);
    elements.analysisExportMenu?.addEventListener("click", handleExportMenuClick);
    document.addEventListener("click", handleExportMenuDocumentClick);
    document.addEventListener("keydown", handleDocumentKeydown);
    elements.analysisEmptyActionButton?.addEventListener("click", () => {
        void openWorkspace("analysis");
    });
    elements.backToDashboardDataButton?.addEventListener("click", () => {
        void openWorkspace("dashboard");
    });
    elements.columnRoleBackdrop?.addEventListener("click", closeColumnRoleModal);
    elements.closeColumnRoleModalButton?.addEventListener("click", closeColumnRoleModal);
    elements.columnRoleSearch?.addEventListener("input", handleColumnRoleSearch);
    elements.columnRoleSelect?.addEventListener("change", renderColumnRoleSelectionState);
    elements.applyColumnRoleButton?.addEventListener("click", () => {
        void applyColumnRoleChange();
    });
    elements.filterBackdrop?.addEventListener("click", closeFilterModal);
    elements.closeFilterModalButton?.addEventListener("click", closeFilterModal);
    elements.analysisGroupBackdrop?.addEventListener("click", closeAnalysisGroupModal);
    elements.closeAnalysisGroupModalButton?.addEventListener("click", closeAnalysisGroupModal);
    elements.analysisGroupLoadAllButton?.addEventListener("click", () => {
        if (state.analysisGroupModalMode === "ngram") {
            void loadAnalysisNgramDocuments({ reset: true });
            return;
        }
        void loadAnalysisGroupDocuments({ reset: true });
    });
    elements.analysisGroupLoadMoreButton?.addEventListener("click", () => {
        if (state.analysisGroupModalMode === "ngram") {
            void loadAnalysisNgramDocuments();
            return;
        }
        void loadAnalysisGroupDocuments();
    });
    elements.analysisGroupDocuments?.addEventListener("click", handleTranslateDocumentClick);
    elements.filterColumnSelect?.addEventListener("change", handleFilterColumnChange);
    elements.filterValueSelect?.addEventListener("change", handleFilterValueChange);
    elements.addFilterButton?.addEventListener("click", () => {
        void handleAddFilter();
    });
    elements.activeFilters?.addEventListener("click", handleFilterRemovalClick);
    elements.analysisResultsActiveFilters?.addEventListener("click", handleFilterRemovalClick);
    elements.verbatimToggle?.addEventListener("change", () => {
        void handlePreviewModeChange();
    });
    elements.tableSlider?.addEventListener("input", handleSliderInput);
    elements.tableWrap?.addEventListener("scroll", handlePreviewTableScroll);
    elements.analysisColumnSelect?.addEventListener("change", handleAnalysisColumnChange);
    elements.analysisMethods?.addEventListener("click", handleAnalysisMethodClick);
    elements.runAnalysisButton?.addEventListener("click", handleRunAnalysis);
    window.addEventListener("resize", syncSliderRange);
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


function handleExportMenuDocumentClick(event) {
    const target = event.target;
    if (!(target instanceof Node)) {
        return;
    }

    if (state.analysisExportMenuOpen) {
        if (!(elements.analysisExportMenu?.contains(target) || elements.analysisExportToggleButton?.contains(target))) {
            state.analysisExportMenuOpen = false;
            renderAnalysisExportControls();
        }
    }
    if (state.dataExportMenuOpen) {
        if (!(elements.dataExportMenu?.contains(target) || elements.dataExportToggleButton?.contains(target))) {
            state.dataExportMenuOpen = false;
            renderDataExportControls();
        }
    }
}


function handleDataExportToggleClick(event) {
    event.stopPropagation();
    if (state.dataExportRunning) {
        return;
    }
    state.dataExportMenuOpen = !state.dataExportMenuOpen;
    renderDataExportControls();
}


function handleDataExportMenuClick(event) {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
        return;
    }
    const scopeButton = target.closest("[data-data-export-scope]");
    if (!(scopeButton instanceof HTMLElement)) {
        return;
    }
    const scope = scopeButton.dataset.dataExportScope;
    state.dataExportMenuOpen = false;
    renderDataExportControls();
    void downloadDataExport(scope);
}


function handleTranslateDocumentClick(event) {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
        return;
    }
    const translateButton = target.closest("[data-translate-document]");
    if (!(translateButton instanceof HTMLElement)) {
        return;
    }
    const documentKey = translateButton.dataset.translateDocument;
    if (!documentKey) {
        return;
    }
    void translateAnalysisDocument(documentKey);
}


function handleFilterRemovalClick(event) {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
        return;
    }
    const removeButton = target.closest("[data-remove-filter]");
    if (!(removeButton instanceof HTMLElement)) {
        return;
    }
    const columnName = removeButton.dataset.removeFilter;
    if (!columnName) {
        return;
    }
    if (columnName === "__all__") {
        void handleClearFilters();
        return;
    }
    void removeActiveFilter(columnName);
}
