import { elements, state } from "./shared.js";
import { downloadAnalysisReport, normalizeAnalysisExportFormat } from "./chartExport.js";
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
} from "./workspace.js";
import { resizeAnalysisPlots } from "./charts.js";


export function bindResultsEvents() {
    elements.uploadDataButton?.addEventListener("click", resetToUploadState);
    elements.openAnalysisButton?.addEventListener("click", () => {
        void openWorkspace("analysis");
    });
    elements.openDataButton?.addEventListener("click", () => {
        void openWorkspace("data");
    });
    elements.dataAnalyseButton?.addEventListener("click", () => {
        void openWorkspace("analysis");
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
    elements.backToDashboardResultsButton?.addEventListener("click", () => {
        void openWorkspace("dashboard");
    });
    elements.downloadAnalysisReportButton?.addEventListener("click", () => {
        void downloadAnalysisReport();
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
    if (!state.analysisExportMenuOpen) {
        return;
    }
    const target = event.target;
    if (!(target instanceof Node)) {
        return;
    }
    if (elements.analysisExportMenu?.contains(target) || elements.analysisExportToggleButton?.contains(target)) {
        return;
    }
    state.analysisExportMenuOpen = false;
    renderAnalysisExportControls();
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
