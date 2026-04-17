import {
    FULL_DATA_VISIBLE_COLUMN_COUNT,
    RESULT_STORAGE_KEY,
    elements,
    state,
} from "./results/shared.js";

const RESULT_HANDOFF_FLAG_KEY = "verbatim-app:pending-handoff";
import {
    analysisCard,
    displayAnalysisMode,
    displayColumnLabel,
    escapeHtml,
    formatCell,
    formatNumber,
    normalizeValue,
    summaryMetric,
} from "./results/utils.js";
import {
    applyActiveFilters,
    configureResultsFilters,
    displayFilterName,
    getColumnRole,
    getFilterDefinition,
    handleAddFilter,
    handleClearFilters,
    handleFilterColumnChange,
    handleFilterValueChange,
    hideAnalysisGroupModalMessage,
    hideColumnRoleMessage,
    hideFilterModalMessage,
    pruneInvalidActiveFilters,
    removeActiveFilter,
    showAnalysisGroupModalMessage,
    showColumnRoleMessage,
    showFilterModalMessage,
} from "./results/filters.js";
import {
    configureResultsCharts,
    downloadAnalysisReport,
    normalizeAnalysisExportFormat,
    resizeAnalysisPlots,
} from "./results/charts.js";
import {
    buildPreviewEmptyMessage,
    configureResultsRows,
    currentPreviewDataset,
    ensureDatasetRowCount,
    getInitialVisibleRowTarget,
    getVisiblePreviewColumns,
    hasActiveFilters,
    maybeLoadMorePreviewRows,
    parseJson,
    refreshFilteredDatasets,
    updatePreviewRowStatus,
} from "./results/rows.js";
import {
    clearAnalysisMessage,
    configureResultsAnalysis,
    getActiveAnalysisRequest,
    handleAnalysisColumnChange,
    handleAnalysisMethodClick,
    handleRunAnalysis,
    renderAnalysisControls,
    renderAnalysisExportControls,
    renderAnalysisMessage,
    renderAnalysisOutput,
    renderAnalysisPanel,
    runAnalysis,
} from "./results/analysis.js";
import {
    closeAnalysisGroupModal,
    loadAnalysisGroupDocuments,
    loadAnalysisNgramDocuments,
    openAnalysisGroupModalByIndex,
    openAnalysisNgramModal,
    translateAnalysisDocument,
} from "./results/modals.js";
import {
    applyColumnRoleChange,
    closeColumnRoleModal,
    configureResultsColumnRoles,
    handleColumnRoleSearch,
    openColumnRoleModal,
    renderColumnRoleSelectionState,
} from "./results/columnRoles.js";

(function () {
configureResultsCharts({
    clearAnalysisMessage,
    handleMissingResultState,
    openAnalysisGroupModalByIndex,
    openAnalysisNgramModal,
    parseJson,
    renderAnalysisExportControls,
    renderAnalysisMessage,
});
configureResultsRows({
    handleMissingResultState,
    renderAnalysisOutput,
    renderAnalysisPanel,
    renderFilterBar,
    renderPreviewTable,
    syncSliderRange,
});
configureResultsFilters({
    closeFilterModal,
    getActiveAnalysisRequest,
    renderFilterBar,
    runAnalysis,
});
configureResultsAnalysis({
    closeAnalysisGroupModal,
    handleMissingResultState,
    renderFilterBar,
    updateWorkspaceVisibility,
});
configureResultsColumnRoles({
    handleMissingResultState,
    persistCurrentPayload,
    renderDashboard,
});

if (elements.dashboardPanel && elements.openAnalysisButton && elements.openDataButton) {
    window.verbatimApplyProcessedResult = applyPayload;
    window.verbatimShowUploadState = resetToUploadState;
    console.info("[Verbatim App][Results] Results controller initialized.");
    window.addEventListener("verbatim:result-ready", (event) => {
        const payload = event instanceof CustomEvent ? event.detail : null;
        console.info("[Verbatim App][Results] Received verbatim:result-ready event.", {
            hasPayload: Boolean(payload),
        });
        if (isValidStoredPayload(payload)) {
            try {
                applyPayload(payload);
            } catch (error) {
                console.error("[Verbatim App][Results] applyPayload failed from event.", error);
                throw error;
            }
            return;
        }
        void loadResultsPage();
    });
    bindEvents();
    void loadResultsPage();
}

function bindEvents() {
    elements.uploadDataButton?.addEventListener("click", () => {
        resetToUploadState();
    });
    elements.openAnalysisButton.addEventListener("click", () => {
        void openWorkspace("analysis");
    });
    elements.openDataButton.addEventListener("click", () => {
        void openWorkspace("data");
    });
    elements.dataAnalyseButton?.addEventListener("click", () => {
        void openWorkspace("analysis");
    });
    elements.openFilterModalButton?.addEventListener("click", () => {
        openFilterModal();
    });
    elements.openAnalysisResultsFilterModalButton?.addEventListener("click", () => {
        openFilterModal();
    });
    elements.editColumnsButton?.addEventListener("click", () => {
        openColumnRoleModal();
    });
    elements.backToDashboardAnalysisButton.addEventListener("click", () => {
        openWorkspace("dashboard");
    });
    elements.backToAnalysisSetupButton?.addEventListener("click", () => {
        openWorkspace("analysis");
    });
    elements.backToDashboardResultsButton?.addEventListener("click", () => {
        openWorkspace("dashboard");
    });
    elements.downloadAnalysisReportButton?.addEventListener("click", () => {
        void downloadAnalysisReport();
    });
    elements.analysisExportToggleButton?.addEventListener("click", (event) => {
        event.stopPropagation();
        if (state.analysisExportRunning) {
            return;
        }
        state.analysisExportMenuOpen = !state.analysisExportMenuOpen;
        renderAnalysisExportControls();
    });
    elements.analysisExportMenu?.addEventListener("click", (event) => {
        const target = event.target;
        if (!(target instanceof HTMLElement)) {
            return;
        }
        const formatButton = target.closest("[data-export-format]");
        if (!(formatButton instanceof HTMLElement)) {
            return;
        }
        const format = normalizeAnalysisExportFormat(formatButton.dataset.exportFormat);
        state.analysisExportFormat = format;
        state.analysisExportMenuOpen = false;
        renderAnalysisExportControls();
    });
    document.addEventListener("click", (event) => {
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
    });
    document.addEventListener("keydown", handleDocumentKeydown);
    elements.analysisEmptyActionButton?.addEventListener("click", () => {
        openWorkspace("analysis");
    });
    elements.backToDashboardDataButton.addEventListener("click", () => {
        openWorkspace("dashboard");
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
    elements.analysisGroupDocuments?.addEventListener("click", (event) => {
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
    });
    elements.filterColumnSelect?.addEventListener("change", handleFilterColumnChange);
    elements.filterValueSelect?.addEventListener("change", handleFilterValueChange);
    elements.addFilterButton?.addEventListener("click", () => {
        void handleAddFilter();
    });
    elements.activeFilters?.addEventListener("click", (event) => {
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
    });
    elements.analysisResultsActiveFilters?.addEventListener("click", (event) => {
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
    });
    elements.verbatimToggle?.addEventListener("change", () => {
        void handlePreviewModeChange();
    });
    elements.tableSlider.addEventListener("input", handleSliderInput);
    elements.tableWrap.addEventListener("scroll", handlePreviewTableScroll);
    elements.analysisColumnSelect.addEventListener("change", handleAnalysisColumnChange);
    elements.analysisMethods.addEventListener("click", handleAnalysisMethodClick);
    elements.runAnalysisButton.addEventListener("click", handleRunAnalysis);
    window.addEventListener("resize", syncSliderRange);
    window.addEventListener("resize", resizeAnalysisPlots);
}

async function loadResultsPage() {
    const pendingHandoff = sessionStorage.getItem(RESULT_HANDOFF_FLAG_KEY) === "1";
    const queryHandoff = isUploadHandoffNavigation();
    const allowRestore = pendingHandoff || queryHandoff;
    console.info("[Verbatim App][Results] loadResultsPage()", {
        pendingHandoff,
        queryHandoff,
        allowRestore,
        isReload: isPageReload(),
    });
    if (isPageReload() && !allowRestore) {
        console.info("[Verbatim App][Results] Clearing stored result because this is a manual reload.");
        sessionStorage.removeItem(RESULT_STORAGE_KEY);
        showEmptyState();
        return;
    }

    if (allowRestore) {
        console.info("[Verbatim App][Results] Allowing stored result restore after upload handoff.");
        sessionStorage.removeItem(RESULT_HANDOFF_FLAG_KEY);
        clearUploadHandoffQuery();
    }

    const payload = readStoredPayload();
    if (!payload) {
        console.warn("[Verbatim App][Results] No stored payload found. Showing upload state.");
        showEmptyState();
        return;
    }

    try {
        applyPayload(payload);
    } catch (error) {
        console.error("[Verbatim App][Results] applyPayload failed during page load.", error);
        throw error;
    }
}

function applyPayload(payload) {
    console.info("[Verbatim App][Results] applyPayload()", {
        resultId: payload?.result_id || null,
        transformedColumns: Array.isArray(payload?.transformed_column_names) ? payload.transformed_column_names.length : 0,
        verbatimColumns: Array.isArray(payload?.analysis_verbatim_column_names) ? payload.analysis_verbatim_column_names.length : 0,
        availableFilters: Array.isArray(payload?.available_filters) ? payload.available_filters.length : 0,
    });
    state.response = payload;
    state.resultId = typeof payload.result_id === "string" ? payload.result_id : null;
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
    state.selectedAnalysisColumn = state.analysisVerbatimColumns[0] || "";
    state.selectedAnalysisModel = "bertopic";
    state.analysisResult = null;
    state.analysisRunning = false;
    state.analysisExportFormat = "pdf";
    state.analysisExportMenuOpen = false;
    state.analysisExportRunning = false;
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
    state.currentWorkspace = "dashboard";
    state.showOnlyVerbatim = false;
    state.previewColumnOffset = 0;
    state.columnSearchTerm = "";

    renderResults(payload);
}

function readStoredPayload() {
    const raw = sessionStorage.getItem(RESULT_STORAGE_KEY);
    if (!raw) {
        console.warn("[Verbatim App][Results] RESULT_STORAGE_KEY missing from sessionStorage.");
        return null;
    }

    try {
        const parsed = JSON.parse(raw);
        if (!isValidStoredPayload(parsed)) {
            console.warn("[Verbatim App][Results] Stored payload is present but invalid.");
            return null;
        }
        console.info("[Verbatim App][Results] Stored payload restored successfully.");
        return parsed;
    } catch {
        console.error("[Verbatim App][Results] Failed to parse stored payload JSON.");
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

function showEmptyState() {
    document.body.classList.add("upload-workspace-active");
    document.body.classList.remove("dashboard-workspace-active");
    document.body.classList.remove("data-workspace-active");
    document.body.classList.remove("analysis-setup-workspace-active");
    document.body.classList.remove("analysis-results-workspace-active");
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
    console.info("[Verbatim App][Results] renderResults()", {
        filename: payload?.filename || null,
    });
    document.body.classList.remove("upload-workspace-active");
    if (elements.emptyState) {
        elements.emptyState.hidden = true;
    }
    document.body.classList.remove("dashboard-workspace-active");
    document.body.classList.remove("data-workspace-active");
    document.body.classList.remove("analysis-setup-workspace-active");
    document.body.classList.remove("analysis-results-workspace-active");
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
    console.info("[Verbatim App][Results] Dashboard view should now be visible.");
    closeFilterModal();
    closeColumnRoleModal();
    closeAnalysisGroupModal();
}

function resetToUploadState() {
    sessionStorage.removeItem(RESULT_STORAGE_KEY);
    sessionStorage.removeItem(RESULT_HANDOFF_FLAG_KEY);
    state.response = null;
    state.resultId = null;
    state.analysisResult = null;
    state.analysisRows = [];
    state.transformedRows = [];
    state.analysisExportFormat = "pdf";
    state.analysisExportMenuOpen = false;
    state.analysisExportRunning = false;
    state.analysisGroupModalMode = "group";
    state.analysisGroupModalGroupId = "";
    state.analysisGroupModalNgramSize = 0;
    state.analysisGroupModalTerm = "";
    state.analysisGroupModalSourceTerm = "";
    state.analysisGroupModalHitCount = 0;
    state.analysisGroupModalTotalCount = 0;
    state.analysisGroupModalBucketLabel = "";
    state.analysisGroupModalDocuments = [];
    state.analysisGroupModalHasMore = false;
    state.analysisGroupModalOffset = 0;
    state.analysisGroupModalLoading = false;
    state.currentWorkspace = "dashboard";
    showEmptyState();
    window.dispatchEvent(new CustomEvent("verbatim:upload-reset"));
    window.scrollTo({ top: 0, behavior: "smooth" });
}

function renderDashboard(payload) {
    const filename = typeof payload.filename === "string" && payload.filename.trim()
        ? payload.filename.trim()
        : "upload.csv";
    const rowCount = Number(payload.transformed_row_count || 0);
    const columnCount = Array.isArray(payload.transformed_column_names) ? payload.transformed_column_names.length : 0;
    const verbatimCount = state.analysisVerbatimColumns.length;
    console.info("[Verbatim App][Results] renderDashboard()", {
        filename,
        rowCount,
        columnCount,
        verbatimCount,
    });

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
            : "No verbatim columns detected — use Edit Columns to assign them.";
    }
}

async function openWorkspace(nextWorkspace) {
    closeAnalysisGroupModal();
    state.currentWorkspace = nextWorkspace;
    updateWorkspaceVisibility();

    if (nextWorkspace === "data") {
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

function updateWorkspaceVisibility() {
    elements.dashboardPanel.hidden = state.currentWorkspace !== "dashboard";
    elements.dataPanel.hidden = state.currentWorkspace !== "data";
    elements.analysisPanel.hidden = state.currentWorkspace !== "analysis" || !state.analysisVerbatimColumns.length;
    elements.analysisResultsPanel.hidden = state.currentWorkspace !== "analysis-results";
    document.body.classList.toggle("dashboard-workspace-active", state.currentWorkspace === "dashboard");
    document.body.classList.toggle("data-workspace-active", state.currentWorkspace === "data");
    document.body.classList.toggle("analysis-setup-workspace-active", state.currentWorkspace === "analysis");
    document.body.classList.toggle("analysis-results-workspace-active", state.currentWorkspace === "analysis-results");
}

function renderFilterBar() {
    if (!elements.filterBar && !elements.analysisResultsFilterBar) {
        return;
    }

    const filters = Array.isArray(state.availableFilters) ? state.availableFilters : [];
    if (elements.filterBar) {
        elements.filterBar.hidden = filters.length === 0;
    }
    if (elements.analysisResultsFilterBar) {
        elements.analysisResultsFilterBar.hidden = filters.length === 0;
    }
    if (!filters.length) {
        return;
    }

    if (!state.selectedFilterColumn || !filters.some((definition) => definition.column_name === state.selectedFilterColumn)) {
        state.selectedFilterColumn = filters[0]?.column_name || "";
    }

    const selectedDefinition = getFilterDefinition(state.selectedFilterColumn);
    const selectedOptions = Array.isArray(selectedDefinition?.options) ? selectedDefinition.options : [];
    if (!state.selectedFilterValue || !selectedOptions.some((option) => option.value === state.selectedFilterValue)) {
        state.selectedFilterValue = selectedOptions[0]?.value || "";
    }

    if (elements.openFilterModalButton) {
        elements.openFilterModalButton.disabled = filters.length === 0;
    }
    if (elements.openAnalysisResultsFilterModalButton) {
        elements.openAnalysisResultsFilterModalButton.disabled = filters.length === 0;
    }

    elements.filterColumnSelect.innerHTML = filters
        .map((definition) => {
            const isSelected = definition.column_name === state.selectedFilterColumn ? " selected" : "";
            return `<option value="${escapeHtml(definition.column_name)}"${isSelected}>${escapeHtml(displayFilterName(definition))}</option>`;
        })
        .join("");

    elements.filterValueSelect.innerHTML = selectedOptions.length
        ? selectedOptions
            .map((option) => {
                const isSelected = option.value === state.selectedFilterValue ? " selected" : "";
                const optionLabel = `${option.value} (${formatNumber(option.count || 0)})`;
                return `<option value="${escapeHtml(option.value)}"${isSelected}>${escapeHtml(optionLabel)}</option>`;
            })
            .join("")
        : '<option value="">No values available</option>';

    elements.filterValueSelect.disabled = !selectedOptions.length;
    elements.addFilterButton.disabled = !state.selectedFilterColumn || !state.selectedFilterValue;
    elements.verbatimToggle.checked = state.showOnlyVerbatim;

    const activeEntries = Object.entries(state.activeFilters);
    if (elements.activeFilters) {
        elements.activeFilters.hidden = activeEntries.length === 0;
    }
    if (elements.analysisResultsActiveFilters) {
        elements.analysisResultsActiveFilters.hidden = activeEntries.length === 0;
    }
    const activeChips = activeEntries
        .map(([columnName, values]) => {
            const definition = getFilterDefinition(columnName);
            const valueLabel = Array.isArray(values) ? values.join(", ") : "";
            return `
                <div class="active-filter-chip">
                    <span class="active-filter-text">${escapeHtml(displayFilterName(definition))}: ${escapeHtml(valueLabel)}</span>
                    <button type="button" class="active-filter-remove" data-remove-filter="${escapeHtml(columnName)}">Remove</button>
                </div>
            `;
        });
    if (activeEntries.length > 1) {
        activeChips.push(`
            <div class="active-filter-chip active-filter-chip-clear">
                <span class="active-filter-text">Clear all</span>
                <button type="button" class="active-filter-remove" data-remove-filter="__all__">Remove</button>
            </div>
        `);
    }
    const chipMarkup = activeChips.join("");
    if (elements.activeFilters) {
        elements.activeFilters.innerHTML = chipMarkup;
    }
    if (elements.analysisResultsActiveFilters) {
        elements.analysisResultsActiveFilters.innerHTML = chipMarkup;
    }

    const hasFilters = hasActiveFilters();
    if (elements.filterActiveNote) {
        elements.filterActiveNote.textContent = hasFilters
            ? "Active metadata filters apply to both the data table and analysis."
            : "Metadata filters apply to both the data table and analysis.";
    }
    if (elements.analysisResultsFilterNote) {
        elements.analysisResultsFilterNote.textContent = hasFilters
            ? "Active metadata filters are updating the current analysis results and plots."
            : "Metadata filters update the current analysis results and plots.";
    }
}

function openFilterModal() {
    if (!elements.filterModal || elements.openFilterModalButton?.disabled) {
        return;
    }
    hideFilterModalMessage();
    elements.filterModal.hidden = false;
    renderFilterBar();
    requestAnimationFrame(() => {
        elements.filterColumnSelect?.focus();
    });
}

function closeFilterModal() {
    if (!elements.filterModal) {
        return;
    }
    elements.filterModal.hidden = true;
    hideFilterModalMessage();
}

function handleDocumentKeydown(event) {
    if (!(event instanceof KeyboardEvent)) {
        return;
    }

    if (event.key === "Escape") {
        if (!elements.analysisGroupModal?.hidden) {
            closeAnalysisGroupModal();
            return;
        }
        if (!elements.columnRoleModal?.hidden) {
            closeColumnRoleModal();
            return;
        }
        if (!elements.filterModal?.hidden) {
            closeFilterModal();
        }
        return;
    }

    if (event.key !== "Tab") {
        return;
    }

    const activeModal = getActiveModalCard();
    if (!(activeModal instanceof HTMLElement)) {
        return;
    }

    trapFocusWithinModal(event, activeModal);
}

function getActiveModalCard() {
    if (!elements.analysisGroupModal?.hidden) {
        return elements.analysisGroupModalCard;
    }
    if (!elements.columnRoleModal?.hidden) {
        return elements.columnRoleModal?.querySelector(".modal-card");
    }
    if (!elements.filterModal?.hidden) {
        return elements.filterModal?.querySelector(".modal-card");
    }
    return null;
}

function trapFocusWithinModal(event, modalCard) {
    const focusable = Array.from(
        modalCard.querySelectorAll(
            'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
    ).filter((element) => element instanceof HTMLElement && !element.hidden && element.offsetParent !== null);

    if (!focusable.length) {
        event.preventDefault();
        modalCard.focus();
        return;
    }

    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const active = document.activeElement;

    if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus();
        return;
    }

    if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
    }
}

function renderPreviewTable(preserveScroll) {
    renderFilterBar();

    const dataset = currentPreviewDataset();
    const allColumns = dataset === "analysis"
        ? state.analysisVerbatimColumns
        : state.transformedColumnNames;
    const previewColumns = getVisiblePreviewColumns(allColumns, dataset);
    const previewRows = dataset === "analysis"
        ? state.analysisRows
        : state.transformedRows;
    const scrollTop = preserveScroll ? elements.tableWrap.scrollTop : 0;
    const scrollLeft = preserveScroll && dataset === "analysis" ? elements.tableWrap.scrollLeft : 0;

    if (!allColumns.length || !previewColumns.length) {
        elements.tableControls.hidden = true;
        elements.tableRowStatus.textContent = "";
        elements.tableEmpty.hidden = false;
        elements.tableWrap.hidden = true;
        elements.previewTable.innerHTML = "";
        return;
    }

    elements.tableControls.hidden = false;

    if (!previewRows.length || !previewColumns.length) {
        updatePreviewRowStatus();
        elements.tableEmpty.textContent = buildPreviewEmptyMessage();
        elements.tableEmpty.hidden = false;
        elements.tableWrap.hidden = true;
        elements.previewTable.innerHTML = "";
        return;
    }

    elements.tableEmpty.textContent = buildPreviewEmptyMessage();
    updatePreviewRowStatus();

    const head = [
        '<th scope="col" class="row-number-header">Row</th>',
        ...previewColumns.map((column) => `<th scope="col">${escapeHtml(displayColumnLabel(column))}</th>`),
    ].join("");

    const body = previewRows
        .map((row, index) => {
            const cells = previewColumns
                .map((column) => `<td>${formatCell(row[column])}</td>`)
                .join("");
            return `<tr><th scope="row" class="row-number-cell">${index + 1}</th>${cells}</tr>`;
        })
        .join("");

    elements.previewTable.innerHTML = `
        <thead>
            <tr>${head}</tr>
        </thead>
        <tbody>${body}</tbody>
    `;

    elements.tableEmpty.hidden = true;
    elements.tableWrap.hidden = false;
    requestAnimationFrame(() => {
        if (preserveScroll) {
            elements.tableWrap.scrollTop = scrollTop;
            if (dataset === "analysis") {
                elements.tableWrap.scrollLeft = scrollLeft;
            }
        }
        syncSliderRange();
    });
}

function focusAnalysisTarget(targetId) {
    if (!targetId) {
        return;
    }

    elements.analysisPanel
        .querySelectorAll(".analysis-item-active, .analysis-ngram-panel-active")
        .forEach((element) => {
            element.classList.remove("analysis-item-active", "analysis-ngram-panel-active");
        });

    const target = document.getElementById(targetId);
    if (!(target instanceof HTMLElement)) {
        return;
    }

    const activeClass = target.classList.contains("analysis-ngram-panel")
        ? "analysis-ngram-panel-active"
        : "analysis-item-active";
    target.classList.add(activeClass);
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    window.setTimeout(() => {
        target.classList.remove(activeClass);
    }, 2200);
}

function handleSliderInput(event) {
    if (currentPreviewDataset() === "analysis") {
        elements.tableWrap.scrollLeft = Number(event.target.value);
        return;
    }

    state.previewColumnOffset = Number(event.target.value);
    renderPreviewTable(true);
}

function handlePreviewTableScroll() {
    if (currentPreviewDataset() === "analysis") {
        syncSliderToScroll();
    }
    void maybeLoadMorePreviewRows();
}

async function handlePreviewModeChange() {
    state.showOnlyVerbatim = Boolean(elements.verbatimToggle.checked);
    state.previewColumnOffset = 0;
    const dataset = currentPreviewDataset();
    await ensureDatasetRowCount(dataset, getInitialVisibleRowTarget(dataset));
    renderPreviewTable(false);
    syncSliderRange();
}

function syncSliderToScroll() {
    if (currentPreviewDataset() !== "analysis") {
        elements.tableSlider.value = `${state.previewColumnOffset}`;
        return;
    }
    elements.tableSlider.value = `${Math.round(elements.tableWrap.scrollLeft)}`;
}

function syncSliderRange() {
    if (elements.tableWrap.hidden) {
        elements.tableControls.hidden = true;
        return;
    }

    if (currentPreviewDataset() !== "analysis") {
        const totalColumns = state.transformedColumnNames.length;
        const maxOffset = Math.max(0, totalColumns - FULL_DATA_VISIBLE_COLUMN_COUNT);
        elements.tableSlider.max = `${maxOffset}`;
        elements.tableSlider.value = `${Math.min(state.previewColumnOffset, maxOffset)}`;
        if (elements.tableSliderLabel) {
            elements.tableSliderLabel.textContent = "Choose which columns to show";
        }
        elements.tableScrollControl.hidden = maxOffset <= 0;
        return;
    }

    const maxScroll = Math.max(0, elements.tableWrap.scrollWidth - elements.tableWrap.clientWidth);
    elements.tableSlider.max = `${Math.round(maxScroll)}`;
    elements.tableSlider.value = `${Math.min(Math.round(elements.tableWrap.scrollLeft), Math.round(maxScroll))}`;
    if (elements.tableSliderLabel) {
        elements.tableSliderLabel.textContent = "Slide across columns";
    }
    elements.tableScrollControl.hidden = maxScroll <= 0;
}

function persistCurrentPayload() {
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
        console.warn("[Verbatim App] Unable to update cached processed result.", error);
    }
}

function handleMissingResultState(message = "The processed result is no longer available. Upload the file again.") {
    console.warn(`[Verbatim App] ${message}`);
    resetToUploadState();
}

})();

