(function () {
const RESULT_STORAGE_KEY = "verbatim-app:last-upload-result";
const ROW_PAGE_SIZE = 250;
const INITIAL_VISIBLE_ROW_TARGET = 250;
const FULL_DATA_ROW_PAGE_SIZE = 50;
const FULL_DATA_INITIAL_VISIBLE_ROW_TARGET = 50;
const FULL_DATA_VISIBLE_COLUMN_COUNT = 12;
const ANALYSIS_MODE_OPTIONS = [
    { key: "bertopic", label: "BERTopic", description: "Groups similar responses into topics and compares topic size." },
    { key: "kmeans", label: "K-means", description: "Splits responses into a fixed number of similarity groups." },
    { key: "hdbscan", label: "Agglomerative", description: "Builds natural clusters by merging the closest responses first." },
    { key: "ngrams", label: "N-grams", description: "Highlights the most repeated words and phrases in the text." },
];

let activeAnalysisAbortController = null;

const state = {
    response: null,
    resultId: null,
    analysisMetadataColumns: [],
    analysisVerbatimColumns: [],
    transformedColumnNames: [],
    analysisColumnNames: [],
    availableFilters: [],
    selectedFilterColumn: "",
    selectedFilterValue: "",
    activeFilters: {},
    showOnlyVerbatim: false,
    transformedRows: [],
    analysisRows: [],
    transformedTotalRows: 0,
    analysisTotalRows: 0,
    transformedUnfilteredTotalRows: 0,
    analysisUnfilteredTotalRows: 0,
    transformedHasMore: false,
    analysisHasMore: false,
    transformedLoading: false,
    analysisLoading: false,
    selectedAnalysisColumn: "",
    selectedAnalysisModel: "bertopic",
    analysisResult: null,
    analysisRunning: false,
    analysisExportFormat: "pdf",
    analysisExportMenuOpen: false,
    analysisExportRunning: false,
    analysisGroupModalMode: "group",
    analysisGroupModalGroupId: "",
    analysisGroupModalNgramSize: 0,
    analysisGroupModalTerm: "",
    analysisGroupModalSourceTerm: "",
    analysisGroupModalHitCount: 0,
    analysisGroupModalTotalCount: 0,
    analysisGroupModalBucketLabel: "",
    analysisGroupModalDocuments: [],
    analysisGroupModalHasMore: false,
    analysisGroupModalOffset: 0,
    analysisGroupModalLoading: false,
    currentWorkspace: "dashboard",
    previewColumnOffset: 0,
    columnSearchTerm: "",
};

const elements = {
    emptyState: document.getElementById("empty-state"),
    uploadView: document.getElementById("upload-view"),
    resultsView: document.getElementById("results-view"),
    stepPill: document.getElementById("step-pill"),
    uploadDataButton: document.getElementById("upload-data-btn"),
    dashboardPanel: document.getElementById("dashboard-panel"),
    dashboardFileName: document.getElementById("dashboard-file-name"),
    dashboardMetrics: document.getElementById("dashboard-metrics"),
    openAnalysisButton: document.getElementById("open-analysis-btn"),
    openDataButton: document.getElementById("open-data-btn"),
    filterBar: document.getElementById("filter-bar"),
    openFilterModalButton: document.getElementById("open-filter-modal-btn"),
    filterColumnSelect: document.getElementById("filter-column-select"),
    filterValueSelect: document.getElementById("filter-value-select"),
    addFilterButton: document.getElementById("add-filter-btn"),
    activeFilters: document.getElementById("active-filters"),
    filterActiveNote: document.getElementById("filter-active-note"),
    filterModal: document.getElementById("filter-modal"),
    filterBackdrop: document.getElementById("filter-backdrop"),
    closeFilterModalButton: document.getElementById("close-filter-modal-btn"),
    filterModalMessage: document.getElementById("filter-modal-message"),
    analysisResultsFilterBar: document.getElementById("analysis-results-filter-bar"),
    analysisResultsActiveFilters: document.getElementById("analysis-results-active-filters"),
    analysisResultsFilterNote: document.getElementById("analysis-results-filter-note"),
    openAnalysisResultsFilterModalButton: document.getElementById("open-analysis-results-filter-modal-btn"),
    tableControls: document.getElementById("table-controls"),
    verbatimToggle: document.getElementById("verbatim-toggle"),
    tableScrollControl: document.getElementById("table-scroll-control"),
    tableSliderLabel: document.getElementById("table-slider-label"),
    tableRowStatus: document.getElementById("table-row-status"),
    tableSlider: document.getElementById("table-slider"),
    tableEmpty: document.getElementById("table-empty"),
    tableWrap: document.getElementById("table-wrap"),
    previewTable: document.getElementById("preview-table"),
    dataPanel: document.getElementById("data-panel"),
    dataAnalyseButton: document.getElementById("data-analyse-btn"),
    editColumnsButton: document.getElementById("edit-columns-btn"),
    backToDashboardDataButton: document.getElementById("back-to-dashboard-data-btn"),
    columnRoleModal: document.getElementById("column-role-modal"),
    columnRoleBackdrop: document.getElementById("column-role-backdrop"),
    closeColumnRoleModalButton: document.getElementById("close-column-role-modal-btn"),
    columnRoleSearch: document.getElementById("column-role-search"),
    columnRoleSelect: document.getElementById("column-role-select"),
    columnRoleCurrent: document.getElementById("column-role-current"),
    columnRoleTypeSelect: document.getElementById("column-role-type-select"),
    applyColumnRoleButton: document.getElementById("apply-column-role-btn"),
    columnRoleMessage: document.getElementById("column-role-message"),
    analysisPanel: document.getElementById("analysis-panel"),
    analysisResultsPanel: document.getElementById("analysis-results-panel"),
    analysisResultsSubtitle: document.getElementById("analysis-results-subtitle"),
    backToDashboardAnalysisButton: document.getElementById("back-to-dashboard-analysis-btn"),
    backToAnalysisSetupButton: document.getElementById("back-to-analysis-setup-btn"),
    backToDashboardResultsButton: document.getElementById("back-to-dashboard-results-btn"),
    analysisEmptyState: document.getElementById("analysis-empty-state"),
    analysisEmptyActionButton: document.getElementById("analysis-empty-action-btn"),
    analysisColumnSelect: document.getElementById("analysis-column-select"),
    analysisMethods: document.getElementById("analysis-methods"),
    analysisMessage: document.getElementById("analysis-message"),
    analysisSummary: document.getElementById("analysis-summary"),
    analysisChart: document.getElementById("analysis-chart"),
    analysisList: document.getElementById("analysis-list"),
    analysisNgramGrid: document.getElementById("analysis-ngram-grid"),
    downloadAnalysisReportButton: document.getElementById("download-analysis-report-btn"),
    analysisExportToggleButton: document.getElementById("analysis-export-toggle-btn"),
    analysisExportMenu: document.getElementById("analysis-export-menu"),
    runAnalysisButton: document.getElementById("run-analysis-btn"),
    analysisGroupModal: document.getElementById("analysis-group-modal"),
    analysisGroupModalCard: document.querySelector("#analysis-group-modal .analysis-group-modal-card"),
    analysisGroupBackdrop: document.getElementById("analysis-group-backdrop"),
    closeAnalysisGroupModalButton: document.getElementById("close-analysis-group-modal-btn"),
    analysisGroupKicker: document.getElementById("analysis-group-kicker"),
    analysisGroupTitle: document.getElementById("analysis-group-title"),
    analysisGroupMeta: document.getElementById("analysis-group-meta"),
    analysisGroupTerms: document.getElementById("analysis-group-terms"),
    analysisGroupModalMessage: document.getElementById("analysis-group-modal-message"),
    analysisGroupExamplesSection: document.getElementById("analysis-group-examples-section"),
    analysisGroupExamplesTitle: document.getElementById("analysis-group-examples-title"),
    analysisGroupExamplesSubtitle: document.getElementById("analysis-group-examples-subtitle"),
    analysisGroupExamples: document.getElementById("analysis-group-examples"),
    analysisGroupLoadAllButton: document.getElementById("analysis-group-load-all-btn"),
    analysisGroupFullSection: document.getElementById("analysis-group-full-section"),
    analysisGroupFullTitle: document.getElementById("analysis-group-full-title"),
    analysisGroupDocuments: document.getElementById("analysis-group-documents"),
    analysisGroupLoadMoreButton: document.getElementById("analysis-group-load-more-btn"),
};

if (elements.dashboardPanel && elements.openAnalysisButton && elements.openDataButton) {
    bindEvents();
    void loadResultsPage();
    window.verbatimApplyProcessedResult = applyPayload;
    window.verbatimShowUploadState = resetToUploadState;
    window.addEventListener("verbatim:result-ready", (event) => {
        const payload = event instanceof CustomEvent ? event.detail : null;
        if (isValidStoredPayload(payload)) {
            applyPayload(payload);
            return;
        }
        void loadResultsPage();
    });
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
    const payload = readStoredPayload();
    if (!payload) {
        showEmptyState();
        return;
    }

    applyPayload(payload);
}

function applyPayload(payload) {
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
    closeFilterModal();
    closeColumnRoleModal();
    closeAnalysisGroupModal();
}

function resetToUploadState() {
    sessionStorage.removeItem(RESULT_STORAGE_KEY);
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

    elements.dashboardFileName.textContent = filename;

    const metrics = [
        summaryMetric("rows", "Rows", formatNumber(rowCount)),
        summaryMetric("columns", "Columns", formatNumber(columnCount)),
        summaryMetric("verbatim", "Verbatim Columns", formatNumber(verbatimCount)),
    ];
    elements.dashboardMetrics.innerHTML = metrics.join("");
    elements.openAnalysisButton.disabled = !verbatimCount;
    elements.openDataButton.disabled = !verbatimCount;
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

function openColumnRoleModal() {
    if (!elements.columnRoleModal) {
        return;
    }
    state.columnSearchTerm = "";
    elements.columnRoleSearch.value = "";
    elements.columnRoleMessage.hidden = true;
    elements.columnRoleModal.hidden = false;
    renderColumnRoleModal();
    requestAnimationFrame(() => {
        elements.columnRoleSearch?.focus();
    });
}

function closeColumnRoleModal() {
    if (!elements.columnRoleModal) {
        return;
    }
    elements.columnRoleModal.hidden = true;
    hideColumnRoleMessage();
}

function openAnalysisGroupModalByIndex(groupIndex) {
    const groups = Array.isArray(state.analysisResult?.groups) ? state.analysisResult.groups : [];
    const group = groups[groupIndex];
    if (!group || !elements.analysisGroupModal) {
        return;
    }

    state.analysisGroupModalMode = "group";
    state.analysisGroupModalGroupId = String(group.group_id || "");
    state.analysisGroupModalNgramSize = 0;
    state.analysisGroupModalTerm = "";
    state.analysisGroupModalSourceTerm = "";
    state.analysisGroupModalHitCount = 0;
    state.analysisGroupModalTotalCount = Number(group.count || 0);
    state.analysisGroupModalBucketLabel = "";
    state.analysisGroupModalDocuments = [];
    state.analysisGroupModalHasMore = false;
    state.analysisGroupModalOffset = 0;
    state.analysisGroupModalLoading = false;
    hideAnalysisGroupModalMessage();
    elements.analysisGroupModal.hidden = false;
    renderAnalysisGroupModal();
    void loadAnalysisGroupDocuments({ reset: true });
}

function openAnalysisNgramModal(bucketIndex, itemIndex) {
    const buckets = Array.isArray(state.analysisResult?.ngram_buckets) ? state.analysisResult.ngram_buckets : [];
    const bucket = buckets[bucketIndex];
    const items = Array.isArray(bucket?.items) ? bucket.items : [];
    const item = items[itemIndex];
    if (!bucket || !item || !elements.analysisGroupModal) {
        return;
    }

    state.analysisGroupModalMode = "ngram";
    state.analysisGroupModalGroupId = "";
    state.analysisGroupModalNgramSize = Number(bucket.ngram_size || 0);
    state.analysisGroupModalTerm = String(item.term || "");
    state.analysisGroupModalSourceTerm = normalizeValue(item.source_term);
    state.analysisGroupModalHitCount = Number(item.count || 0);
    state.analysisGroupModalTotalCount = Number(item.document_count || 0);
    state.analysisGroupModalBucketLabel = String(bucket.label || `${bucket.ngram_size}-grams`);
    state.analysisGroupModalDocuments = [];
    state.analysisGroupModalHasMore = false;
    state.analysisGroupModalOffset = 0;
    state.analysisGroupModalLoading = false;
    hideAnalysisGroupModalMessage();
    elements.analysisGroupModal.hidden = false;
    renderAnalysisGroupModal();
    void loadAnalysisNgramDocuments({ reset: true });
}

function closeAnalysisGroupModal() {
    if (!elements.analysisGroupModal) {
        return;
    }
    elements.analysisGroupModal.hidden = true;
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
    hideAnalysisGroupModalMessage();
}

function getActiveAnalysisGroup() {
    const groupId = state.analysisGroupModalGroupId;
    if (state.analysisGroupModalMode !== "group" || !groupId || !Array.isArray(state.analysisResult?.groups)) {
        return null;
    }
    return state.analysisResult.groups.find((group) => String(group.group_id || "") === groupId) || null;
}

function syncAnalysisGroupModalAppearance() {
    if (!(elements.analysisGroupModalCard instanceof HTMLElement)) {
        return;
    }
    elements.analysisGroupModalCard.classList.toggle(
        "analysis-group-modal-card-ngram",
        state.analysisGroupModalMode === "ngram" || state.analysisGroupModalMode === "group",
    );
}

function renderAnalysisModalStatPills(items) {
    return items
        .filter((item) => item && item.value)
        .map((item) => `
            <span class="analysis-group-stat-pill">
                <span class="analysis-group-stat-icon" aria-hidden="true"></span>
                <span>${escapeHtml(item.value)}</span>
            </span>
        `)
        .join("");
}

function renderAnalysisModalContext(items) {
    return items
        .filter(Boolean)
        .map((item) => `<span>${escapeHtml(String(item))}</span>`)
        .join("");
}

function renderAnalysisGroupModal() {
    syncAnalysisGroupModalAppearance();
    if (state.analysisGroupModalMode === "ngram") {
        renderAnalysisNgramModal();
        return;
    }

    const group = getActiveAnalysisGroup();
    if (!group) {
        closeAnalysisGroupModal();
        return;
    }

    const count = Number(state.analysisGroupModalTotalCount || group.count || 0);
    const loadedCount = state.analysisGroupModalDocuments.length;
    const percent = typeof group.share === "number" ? Math.round(group.share * 100) : 0;
    const modelKey = state.analysisResult?.model_key || state.selectedAnalysisModel;
    const subjectLabel = modelKey === "bertopic" ? "Theme" : "Group";
    const contextItems = [
        group.translated && !group.ai_generated ? "Translated label" : "",
        Array.isArray(group.terms) && group.terms.length
            ? `Top terms: ${group.terms.slice(0, 4).join(", ")}`
            : "",
        group.is_noise ? "Outlier bucket" : "",
    ];
    const detailsMarkup = renderAnalysisModalContext(contextItems);

    if (elements.analysisGroupTitle) {
        elements.analysisGroupTitle.textContent = group.label || "Unlabelled group";
    }
    if (elements.analysisGroupKicker) {
        elements.analysisGroupKicker.textContent = `${subjectLabel} Responses`;
    }
    if (elements.analysisGroupMeta) {
        elements.analysisGroupMeta.innerHTML = renderAnalysisModalStatPills([
            { value: `${formatNumber(count)} responses` },
            { value: percent ? `${percent}% usable` : "" },
        ]);
    }
    if (elements.analysisGroupTerms) {
        elements.analysisGroupTerms.hidden = !detailsMarkup;
        elements.analysisGroupTerms.innerHTML = detailsMarkup;
    }
    if (elements.analysisGroupExamplesSection) {
        elements.analysisGroupExamplesSection.hidden = true;
    }
    if (elements.analysisGroupExamplesTitle) {
        elements.analysisGroupExamplesTitle.textContent = "";
    }
    if (elements.analysisGroupExamplesSubtitle) {
        elements.analysisGroupExamplesSubtitle.textContent = "";
    }
    if (elements.analysisGroupExamples) {
        elements.analysisGroupExamples.innerHTML = "";
    }
    if (elements.analysisGroupLoadAllButton) {
        elements.analysisGroupLoadAllButton.hidden = true;
    }
    if (elements.analysisGroupFullSection) {
        elements.analysisGroupFullSection.hidden = false;
    }
    if (elements.analysisGroupFullTitle) {
        elements.analysisGroupFullTitle.textContent = loadedCount
            ? `${subjectLabel} Responses (${formatNumber(loadedCount)} of ${formatNumber(count)})`
            : `${subjectLabel} Responses`;
    }
    if (elements.analysisGroupDocuments) {
        if (loadedCount) {
            elements.analysisGroupDocuments.innerHTML = state.analysisGroupModalDocuments
                .map((document) => renderAnalysisDocumentCard(document))
                .join("");
        } else if (state.analysisGroupModalLoading) {
            elements.analysisGroupDocuments.innerHTML = `<p class="analysis-sample">Loading ${subjectLabel.toLowerCase()} responses...</p>`;
        } else {
            elements.analysisGroupDocuments.innerHTML = `<p class="analysis-sample">No responses were found for this ${subjectLabel.toLowerCase()}.</p>`;
        }
    }
    if (elements.analysisGroupLoadMoreButton) {
        elements.analysisGroupLoadMoreButton.hidden = !state.analysisGroupModalHasMore;
        elements.analysisGroupLoadMoreButton.disabled = state.analysisGroupModalLoading;
        elements.analysisGroupLoadMoreButton.textContent = state.analysisGroupModalLoading && state.analysisGroupModalDocuments.length > 0
            ? "Loading..."
            : "Load more";
    }
}

function renderAnalysisNgramModal() {
    if (!elements.analysisGroupModal || !state.analysisGroupModalTerm) {
        closeAnalysisGroupModal();
        return;
    }

    if (elements.analysisGroupKicker) {
        elements.analysisGroupKicker.textContent = "Phrase Matches";
    }
    if (elements.analysisGroupTitle) {
        elements.analysisGroupTitle.textContent = state.analysisGroupModalTerm;
    }
    if (elements.analysisGroupMeta) {
        const totalCount = Number(state.analysisGroupModalTotalCount || 0);
        const hitCount = Number(state.analysisGroupModalHitCount || 0);
        elements.analysisGroupMeta.innerHTML = renderAnalysisModalStatPills([
            { value: `${formatNumber(totalCount)} matching response${totalCount === 1 ? "" : "s"}` },
            { value: `${formatNumber(hitCount)} total hit${hitCount === 1 ? "" : "s"}` },
        ]);
    }
    if (elements.analysisGroupTerms) {
        const detailsMarkup = renderAnalysisModalContext([
            state.analysisGroupModalBucketLabel,
            state.analysisGroupModalSourceTerm ? `Original phrase: ${state.analysisGroupModalSourceTerm}` : "",
        ]);
        elements.analysisGroupTerms.hidden = !detailsMarkup;
        elements.analysisGroupTerms.innerHTML = detailsMarkup;
    }
    if (elements.analysisGroupExamplesSection) {
        elements.analysisGroupExamplesSection.hidden = true;
    }
    if (elements.analysisGroupExamplesSubtitle) {
        elements.analysisGroupExamplesSubtitle.textContent = "";
    }
    if (elements.analysisGroupExamples) {
        elements.analysisGroupExamples.innerHTML = "";
    }
    if (elements.analysisGroupLoadAllButton) {
        elements.analysisGroupLoadAllButton.hidden = true;
    }
    if (elements.analysisGroupFullSection) {
        elements.analysisGroupFullSection.hidden = false;
    }
    if (elements.analysisGroupFullTitle) {
        const totalCount = Number(state.analysisGroupModalTotalCount || 0);
        elements.analysisGroupFullTitle.textContent = totalCount
            ? `Matching Responses (${formatNumber(state.analysisGroupModalDocuments.length)} of ${formatNumber(totalCount)})`
            : "Matching Responses";
    }
    if (elements.analysisGroupDocuments) {
        if (state.analysisGroupModalDocuments.length) {
            elements.analysisGroupDocuments.innerHTML = state.analysisGroupModalDocuments
                .map((document) => renderAnalysisDocumentCard(document))
                .join("");
        } else if (state.analysisGroupModalLoading) {
            elements.analysisGroupDocuments.innerHTML = '<p class="analysis-sample">Loading matching responses...</p>';
        } else {
            elements.analysisGroupDocuments.innerHTML = '<p class="analysis-sample">No matching responses were found for this phrase.</p>';
        }
    }
    if (elements.analysisGroupLoadMoreButton) {
        elements.analysisGroupLoadMoreButton.hidden = !state.analysisGroupModalHasMore;
        elements.analysisGroupLoadMoreButton.disabled = state.analysisGroupModalLoading;
        elements.analysisGroupLoadMoreButton.textContent = state.analysisGroupModalLoading && state.analysisGroupModalDocuments.length > 0
            ? "Loading..."
            : "Load more";
    }
}

function renderAnalysisExampleCard(example) {
    return `
        <blockquote class="analysis-example">
            <div class="analysis-example-header">
                <span class="analysis-example-pill">Row</span>
                <span class="analysis-example-row">Row ${Number(example.row_number || 0)}</span>
                ${example.translated ? '<span class="analysis-example-flag">Translated</span>' : ""}
            </div>
            <p>${escapeHtml(example.text || "")}</p>
            ${example.translated && normalizeValue(example.source_text)
                ? `<p class="analysis-example-source"><strong>Original:</strong> ${escapeHtml(example.source_text || "")}</p>`
                : ""}
        </blockquote>
    `;
}

function renderAnalysisDocumentCard(document) {
    return `
        <blockquote class="analysis-example analysis-example-full">
            <div class="analysis-example-header">
                <span class="analysis-example-pill">Row ${Number(document.row_number || 0)}</span>
            </div>
            <p>${escapeHtml(document.text || "")}</p>
        </blockquote>
    `;
}

async function loadAnalysisGroupDocuments({ reset = false } = {}) {
    const group = getActiveAnalysisGroup();
    if (!group || !state.resultId || state.analysisGroupModalLoading) {
        return;
    }

    const offset = reset ? 0 : state.analysisGroupModalOffset;
    state.analysisGroupModalLoading = true;
    hideAnalysisGroupModalMessage();
    renderAnalysisGroupModal();

    try {
        const query = new URLSearchParams({
            group_id: String(group.group_id || ""),
            offset: String(offset),
            limit: String(FULL_DATA_ROW_PAGE_SIZE),
        });
        const response = await fetch(`/analysis-group-documents/${encodeURIComponent(state.resultId)}?${query.toString()}`);
        if (response.status === 401) {
            sessionStorage.removeItem(RESULT_STORAGE_KEY);
            window.location.assign("/login");
            return;
        }
        const payload = await parseJson(response);
        if (!response.ok) {
            throw new Error(payload.detail || "Unable to load group responses.");
        }

        const documents = Array.isArray(payload.documents) ? payload.documents : [];
        state.analysisGroupModalDocuments = reset
            ? documents
            : state.analysisGroupModalDocuments.concat(documents);
        state.analysisGroupModalOffset = Number(payload.offset || 0) + documents.length;
        state.analysisGroupModalHasMore = Boolean(payload.has_more);
        state.analysisGroupModalTotalCount = Number(payload.total_count || state.analysisGroupModalTotalCount || group.count || 0);
    } catch (error) {
        const message = error instanceof Error ? error.message : "Unable to load group responses.";
        showAnalysisGroupModalMessage("error", message);
    } finally {
        state.analysisGroupModalLoading = false;
        renderAnalysisGroupModal();
    }
}

async function loadAnalysisNgramDocuments({ reset = false } = {}) {
    if (
        state.analysisGroupModalMode !== "ngram"
        || !state.resultId
        || !state.analysisGroupModalTerm
        || !state.analysisGroupModalNgramSize
        || state.analysisGroupModalLoading
    ) {
        return;
    }

    const offset = reset ? 0 : state.analysisGroupModalOffset;
    const lookupTerm = state.analysisGroupModalSourceTerm || state.analysisGroupModalTerm;
    state.analysisGroupModalLoading = true;
    hideAnalysisGroupModalMessage();
    renderAnalysisGroupModal();

    try {
        const query = new URLSearchParams({
            ngram_size: String(state.analysisGroupModalNgramSize),
            term: lookupTerm,
            offset: String(offset),
            limit: String(FULL_DATA_ROW_PAGE_SIZE),
        });
        const response = await fetch(`/analysis-ngram-documents/${encodeURIComponent(state.resultId)}?${query.toString()}`);
        if (response.status === 401) {
            sessionStorage.removeItem(RESULT_STORAGE_KEY);
            window.location.assign("/login");
            return;
        }
        const payload = await parseJson(response);
        if (!response.ok) {
            throw new Error(payload.detail || "Unable to load matching responses.");
        }

        const documents = Array.isArray(payload.documents) ? payload.documents : [];
        state.analysisGroupModalDocuments = reset
            ? documents
            : state.analysisGroupModalDocuments.concat(documents);
        state.analysisGroupModalOffset = Number(payload.offset || 0) + documents.length;
        state.analysisGroupModalHasMore = Boolean(payload.has_more);
        state.analysisGroupModalTotalCount = Number(payload.total_count || state.analysisGroupModalTotalCount || 0);
        state.analysisGroupModalHitCount = Number(payload.hit_count || state.analysisGroupModalHitCount || 0);
    } catch (error) {
        const message = error instanceof Error ? error.message : "Unable to load matching responses.";
        showAnalysisGroupModalMessage("error", message);
    } finally {
        state.analysisGroupModalLoading = false;
        renderAnalysisGroupModal();
    }
}

function renderColumnRoleModal() {
    const allColumns = Array.isArray(state.transformedColumnNames) ? state.transformedColumnNames : [];
    const searchTerm = state.columnSearchTerm.trim().toLowerCase();
    const filteredColumns = allColumns.filter((column) => displayColumnLabel(column).toLowerCase().includes(searchTerm));
    const currentValue = elements.columnRoleSelect.value;
    const selectedValue = filteredColumns.includes(currentValue)
        ? currentValue
        : (filteredColumns[0] || "");

    elements.columnRoleSelect.innerHTML = filteredColumns
        .map((column) => `<option value="${escapeHtml(column)}">${escapeHtml(displayColumnLabel(column))}</option>`)
        .join("");
    if (selectedValue) {
        elements.columnRoleSelect.value = selectedValue;
    }
    elements.applyColumnRoleButton.disabled = !selectedValue;
    renderColumnRoleSelectionState();
}

function renderColumnRoleSelectionState() {
    const columnName = elements.columnRoleSelect.value;
    if (!columnName) {
        elements.columnRoleCurrent.textContent = "Current role: no matching column";
        elements.applyColumnRoleButton.disabled = true;
        return;
    }

    const currentRole = getColumnRole(columnName);
    elements.columnRoleCurrent.textContent = `Current role: ${currentRole}`;
    if (currentRole === "metadata" || currentRole === "verbatim") {
        elements.columnRoleTypeSelect.value = currentRole;
    }
    elements.applyColumnRoleButton.disabled = false;
}

function handleColumnRoleSearch(event) {
    const target = event.target;
    if (!(target instanceof HTMLInputElement)) {
        return;
    }
    state.columnSearchTerm = target.value;
    renderColumnRoleModal();
}

async function applyColumnRoleChange() {
    const columnName = elements.columnRoleSelect.value;
    const role = elements.columnRoleTypeSelect.value;
    if (!columnName || !role || !state.resultId) {
        return;
    }

    elements.applyColumnRoleButton.disabled = true;
    showColumnRoleMessage("neutral", "Updating column assignment...");

    try {
        const response = await fetch(`/result-columns/${encodeURIComponent(state.resultId)}`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                column_name: columnName,
                role,
            }),
        });
        if (response.status === 401) {
            sessionStorage.removeItem(RESULT_STORAGE_KEY);
            window.location.assign("/login");
            return;
        }
        if (response.status === 404) {
            const payload = await parseJson(response);
            handleMissingResultState(payload.detail || "The processed result is no longer available.");
            return;
        }
        const payload = await parseJson(response);
        if (!response.ok) {
            throw new Error(payload.detail || "Unable to update the column assignment.");
        }

        state.analysisMetadataColumns = Array.isArray(payload.analysis_metadata_column_names)
            ? payload.analysis_metadata_column_names
            : [];
        state.analysisVerbatimColumns = Array.isArray(payload.analysis_verbatim_column_names)
            ? payload.analysis_verbatim_column_names
            : [];
        state.analysisColumnNames = Array.isArray(payload.analysis_column_names)
            ? payload.analysis_column_names
            : [];
        state.analysisTotalRows = Number(payload.analysis_row_count || 0);
        state.availableFilters = Array.isArray(payload.available_filters)
            ? payload.available_filters
            : [];
        pruneInvalidActiveFilters();
        if (!state.analysisVerbatimColumns.includes(state.selectedAnalysisColumn)) {
            state.selectedAnalysisColumn = state.analysisVerbatimColumns[0] || "";
        }
        state.analysisResult = null;
        await refreshFilteredDatasets();
        persistCurrentPayload();
        renderDashboard(state.response || {});
        renderColumnRoleModal();
        showColumnRoleMessage("success", "Column assignment updated.");
    } catch (error) {
        const message = error instanceof Error ? error.message : "Unable to update the column assignment.";
        showColumnRoleMessage("error", message);
    } finally {
        renderColumnRoleSelectionState();
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

function renderAnalysisPanel() {
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

function renderAnalysisControls() {
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

function renderAnalysisOutput() {
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
                <p class="analysis-sample">The analysis completed, but it did not produce any usable themes or groups for the current filtered sample.</p>
            </div>
        `;
    renderAnalysisChart(groups, Array.isArray(result.scatter_points) ? result.scatter_points : []);
}

function renderAnalysisExportControls() {
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
            : "Download Report";
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

function renderAnalysisResultsHeader() {
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

function setAnalysisEmptyState(show) {
    if (elements.analysisEmptyState) {
        elements.analysisEmptyState.hidden = !show;
    }
}

function renderAnalysisMessage(kind, message) {
    elements.analysisMessage.hidden = false;
    elements.analysisMessage.className = `analysis-message analysis-message-${kind}`;
    elements.analysisMessage.textContent = message;
}

function clearAnalysisMessage() {
    if (!elements.analysisMessage) {
        return;
    }
    elements.analysisMessage.hidden = true;
    elements.analysisMessage.textContent = "";
    elements.analysisMessage.className = "analysis-message";
}

function renderAnalysisChart(groups, scatterPoints = []) {
    if (!groups.length) {
        clearAnalysisChart();
        return;
    }

    const modelKey = state.analysisResult?.model_key || state.selectedAnalysisModel;
    if (modelKey === "kmeans" && Array.isArray(scatterPoints) && scatterPoints.length) {
        renderKmeansScatterChart(scatterPoints);
        return;
    }
    const isThemeView = modelKey === "bertopic";
    const subjectLabel = isThemeView ? "theme" : "group";
    const yAxisLabel = isThemeView ? "Theme name" : "Group name";
    const chartTitle = isThemeView
        ? "How responses are spread across themes"
        : "How responses are spread across groups";
    const chartCaption = `Hover to see the number of responses in each ${subjectLabel}. Click a bar to open the matching ${subjectLabel} responses.`;

    elements.analysisChart.hidden = false;
    elements.analysisChart.innerHTML = `
        <div class="analysis-chart-copy">
            <h4 class="analysis-chart-title">${escapeHtml(chartTitle)}</h4>
            <p class="analysis-chart-caption">${escapeHtml(chartCaption)}</p>
        </div>
        <div class="analysis-plot-shell">
            <div class="analysis-plot-surface" id="analysis-group-plot"></div>
        </div>
    `;

    const plotContainer = document.getElementById("analysis-group-plot");
    const rendered = renderInteractiveGroupChart(plotContainer, groups, {
        chartTitle,
        yAxisLabel,
    });
    if (!rendered && plotContainer instanceof HTMLElement) {
        plotContainer.outerHTML = renderFallbackGroupChart(groups);
    }
    queueAnalysisPlotResize();
}

function renderKmeansScatterChart(scatterPoints) {
    elements.analysisChart.hidden = false;
    elements.analysisChart.innerHTML = `
        <div class="analysis-plot-shell analysis-plot-shell-wide">
            <div class="analysis-plot-surface analysis-plot-surface-wide" id="analysis-kmeans-plot"></div>
        </div>
    `;

    const plotContainer = document.getElementById("analysis-kmeans-plot");
    const rendered = renderInteractiveKmeansScatterChart(plotContainer, scatterPoints);
    if (!rendered && plotContainer instanceof HTMLElement) {
        plotContainer.outerHTML = `
            <div class="analysis-chart-fallback">
                <p class="analysis-chart-fallback-note">Interactive charts are unavailable right now, so the grouped response cards below show the result instead.</p>
            </div>
        `;
    }
    queueAnalysisPlotResize();
}

function renderNgramCharts(buckets) {
    if (!Array.isArray(buckets) || !buckets.length) {
        clearAnalysisChart();
        return;
    }

    elements.analysisChart.hidden = false;
    elements.analysisChart.innerHTML = `
        <div class="analysis-chart-copy">
            <h4 class="analysis-chart-title">Most common words and phrases in the selected responses</h4>
            <p class="analysis-chart-caption">Hover to see how often each word or phrase appears. Click a bar to open the matching responses.</p>
        </div>
        <div class="analysis-plot-grid">
            ${buckets
                .map((bucket, index) => `
                    <div class="analysis-plot-card">
                        <div class="analysis-plot-surface" id="analysis-ngram-plot-${index}"></div>
                    </div>
                `)
                .join("")}
        </div>
    `;

    const plotly = getPlotly();
    if (!plotly) {
        elements.analysisChart.insertAdjacentHTML(
            "beforeend",
            '<p class="analysis-chart-fallback">Interactive charts are unavailable right now, so matching responses cannot be opened from this view.</p>',
        );
        return;
    }

    buckets.forEach((bucket, index) => {
        const plotContainer = document.getElementById(`analysis-ngram-plot-${index}`);
        renderInteractiveNgramChart(plotContainer, bucket, index);
    });
    queueAnalysisPlotResize();
}

function renderInteractiveGroupChart(plotContainer, groups, { chartTitle, yAxisLabel }) {
    const plotly = getPlotly();
    if (!plotly || !(plotContainer instanceof HTMLElement)) {
        return false;
    }

    const sortedGroups = groups
        .map((group, index) => ({ group, index }))
        .sort((left, right) => Number(right.group.count || 0) - Number(left.group.count || 0));
    const subjectLabel = yAxisLabel === "Theme name" ? "theme" : "group";
    const figureHeight = Math.max(180, sortedGroups.length * 30);

    const plotPromise = plotly.newPlot(
        plotContainer,
        [
            {
                type: "bar",
                orientation: "h",
                y: sortedGroups.map(({ group }) => wrapPlotLabel(group.label || "Unlabelled group", 18)),
                x: sortedGroups.map(({ group }) => Number(group.count || 0)),
                marker: {
                    color: sortedGroups.map(({ group }) => group.is_noise ? "#b8ac9f" : "#4f7a63"),
                    line: {
                        color: sortedGroups.map(({ group }) => group.is_noise ? "#8d8275" : "#355847"),
                        width: 1,
                    },
                },
                customdata: sortedGroups.map(({ group, index }) => ([
                    index,
                    group.label || "Unlabelled group",
                    buildPercentLabel(group.share),
                    buildExampleRowLabel(group.examples),
                    normalizeValue(group.comment),
                ])),
                hovertemplate: [
                    "<b>%{customdata[1]}</b>",
                    "Number of responses: %{x}",
                    "Share of usable responses: %{customdata[2]}",
                    "Representative rows: %{customdata[3]}",
                    "%{customdata[4]}",
                    "<extra></extra>",
                ].join("<br>"),
            },
        ],
        {
            title: {
                text: chartTitle,
                x: 0,
                xanchor: "left",
            },
            height: figureHeight,
            margin: {
                t: 28,
                r: 12,
                b: 36,
                l: 132,
            },
            paper_bgcolor: "rgba(0, 0, 0, 0)",
            plot_bgcolor: "rgba(255, 250, 242, 0.72)",
            font: {
                family: "\"Segoe UI\", Aptos, sans-serif",
                color: "#3d352d",
                size: 8,
            },
            bargap: 0.28,
            xaxis: {
                title: {
                    text: "Number of responses",
                },
                gridcolor: "rgba(89, 68, 42, 0.1)",
                zeroline: false,
            },
            yaxis: {
                title: {
                    text: yAxisLabel,
                },
                automargin: true,
                autorange: "reversed",
            },
        },
        {
            displaylogo: false,
            responsive: true,
            modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d"],
            toImageButtonOptions: {
                filename: `verbatim-${subjectLabel}-distribution`,
            },
        },
    );

    if (plotPromise && typeof plotPromise.then === "function") {
        plotPromise.then(() => {
            if (typeof plotContainer.on === "function") {
                plotContainer.on("plotly_click", (event) => {
                    const point = event?.points?.[0];
                    const groupIndex = Number(point?.customdata?.[0]);
                    if (Number.isFinite(groupIndex)) {
                        openAnalysisGroupModalByIndex(groupIndex);
                    }
                });
            }
        });
    }

    return true;
}

function renderInteractiveKmeansScatterChart(plotContainer, scatterPoints) {
    const plotly = getPlotly();
    if (!plotly || !(plotContainer instanceof HTMLElement)) {
        return false;
    }

    const colorPalette = [
        "#4f7a63",
        "#c7923f",
        "#b7685f",
        "#6a7fb3",
        "#8b6fa5",
        "#5f9ea0",
        "#a86d5d",
        "#7c8c55",
        "#9b7f67",
    ];
    const groupedPoints = new Map();
    scatterPoints.forEach((point) => {
        const groupKey = String(point.group_id || "");
        const bucket = groupedPoints.get(groupKey) || {
            groupId: groupKey,
            groupLabel: point.group_label || "Unlabelled group",
            points: [],
        };
        bucket.points.push(point);
        groupedPoints.set(groupKey, bucket);
    });

    const traces = Array.from(groupedPoints.values()).map((bucket, index) => ({
        type: "scatter",
        mode: "markers",
        name: bucket.groupLabel,
        x: bucket.points.map((point) => Number(point.x || 0)),
        y: bucket.points.map((point) => Number(point.y || 0)),
        marker: {
            size: 16,
            color: colorPalette[index % colorPalette.length],
            line: {
                color: "#ffffff",
                width: 1.4,
            },
            opacity: 0.88,
        },
        customdata: bucket.points.map((point) => ([
            point.row_number || 0,
            point.group_id || "",
            point.group_label || "Unlabelled group",
            point.text || "",
        ])),
        hovertemplate: [
            "<b>%{customdata[2]}</b>",
            "Row: %{customdata[0]}",
            "Response: %{customdata[3]}",
            "<extra></extra>",
        ].join("<br>"),
    }));

    const viewportWidth = Math.max(
        window.innerWidth || 0,
        document.documentElement?.clientWidth || 0,
    );
    const plotWidth = Math.round(Math.min(1275, Math.max(810, viewportWidth * 0.81)));
    const plotHeight = Math.round(Math.min(735, Math.max(540, plotWidth * 0.56)));
    const legendMargin = viewportWidth <= 1180 ? 250 : viewportWidth <= 1440 ? 300 : 340;

    const plotPromise = plotly.newPlot(
        plotContainer,
        traces,
        {
            width: plotWidth,
            height: plotHeight,
            margin: {
                t: 40,
                r: legendMargin,
                b: 96,
                l: 96,
            },
            paper_bgcolor: "rgba(0, 0, 0, 0)",
            plot_bgcolor: "rgba(255, 250, 242, 0.72)",
            font: {
                family: "\"Segoe UI Variable Text\", Inter, \"Segoe UI\", Arial, sans-serif",
                color: "#3d352d",
                size: 19,
            },
            xaxis: {
                title: {
                    text: "Position on response map",
                    font: {
                        size: 20,
                    },
                },
                zeroline: false,
                gridcolor: "rgba(89, 68, 42, 0.08)",
                tickfont: {
                    size: 16,
                },
            },
            yaxis: {
                title: {
                    text: "Position on response map",
                    font: {
                        size: 20,
                    },
                },
                zeroline: false,
                gridcolor: "rgba(89, 68, 42, 0.08)",
                tickfont: {
                    size: 16,
                },
            },
            legend: {
                orientation: "v",
                yanchor: "top",
                y: 1,
                xanchor: "left",
                x: 1.03,
                font: {
                    size: 17,
                },
                itemsizing: "constant",
            },
        },
        {
            displaylogo: false,
            responsive: true,
            modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d"],
            toImageButtonOptions: {
                filename: "verbatim-kmeans-response-map",
            },
        },
    );

    if (plotPromise && typeof plotPromise.then === "function") {
        plotPromise.then(() => {
            if (typeof plotContainer.on === "function") {
                plotContainer.on("plotly_click", (event) => {
                    const point = event?.points?.[0];
                    const groupId = String(point?.customdata?.[1] || "");
                    const groupIndex = Array.isArray(state.analysisResult?.groups)
                        ? state.analysisResult.groups.findIndex((group) => String(group.group_id) === groupId)
                        : -1;
                    if (groupIndex >= 0) {
                        openAnalysisGroupModalByIndex(groupIndex);
                    }
                });
            }
        });
    }

    return true;
}

function renderInteractiveNgramChart(plotContainer, bucket, bucketIndex) {
    const plotly = getPlotly();
    if (!plotly || !(plotContainer instanceof HTMLElement)) {
        return false;
    }

    const items = Array.isArray(bucket.items) ? bucket.items.slice(0, 10) : [];
    const label = bucket.label || `${bucket.ngram_size}-grams`;
    const itemTypeLabel = Number(bucket.ngram_size || 0) === 1 ? "Word" : "Phrase";
    const figureHeight = Math.max(160, items.length * 22 + 60);
    const colorsBySize = {
        1: "#4f7a63",
        2: "#c7923f",
        3: "#b7685f",
    };

    const plotPromise = plotly.newPlot(
        plotContainer,
        [
            {
                type: "bar",
                orientation: "h",
                y: items.map((item) => wrapPlotLabel(item.term || "", 16)),
                x: items.map((item) => Number(item.count || 0)),
                marker: {
                    color: colorsBySize[Number(bucket.ngram_size || 0)] || "#7a6b5e",
                },
                customdata: items.map((item, itemIndex) => [
                    item.term || "",
                    label,
                    itemIndex,
                    Number(item.document_count || 0),
                ]),
                hovertemplate: [
                    "<b>%{customdata[0]}</b>",
                    "Number of times it appears: %{x}",
                    "Matching responses: %{customdata[3]}",
                    "Phrase list: %{customdata[1]}",
                    "<extra></extra>",
                ].join("<br>"),
            },
        ],
        {
            title: {
                text: label,
                x: 0,
                xanchor: "left",
            },
            height: figureHeight,
            margin: {
                t: 28,
                r: 12,
                b: 36,
                l: 88,
            },
            paper_bgcolor: "rgba(0, 0, 0, 0)",
            plot_bgcolor: "rgba(255, 250, 242, 0.72)",
            font: {
                family: "\"Segoe UI\", Aptos, sans-serif",
                color: "#3d352d",
                size: 8,
            },
            bargap: 0.26,
            xaxis: {
                title: {
                    text: `Number of times the ${itemTypeLabel.toLowerCase()} appears`,
                },
                gridcolor: "rgba(89, 68, 42, 0.1)",
                zeroline: false,
            },
            yaxis: {
                title: {
                    text: itemTypeLabel,
                },
                automargin: true,
                autorange: "reversed",
            },
        },
        {
            displaylogo: false,
            responsive: true,
            modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d"],
            toImageButtonOptions: {
                filename: `verbatim-${label.toLowerCase().replaceAll(" ", "-")}`,
            },
        },
    );

    if (plotPromise && typeof plotPromise.then === "function") {
        plotPromise.then(() => {
            if (typeof plotContainer.on === "function") {
                plotContainer.on("plotly_click", (event) => {
                    const point = event?.points?.[0];
                    const itemIndex = Number(point?.customdata?.[2]);
                    if (Number.isFinite(itemIndex)) {
                        openAnalysisNgramModal(bucketIndex, itemIndex);
                    }
                });
            }
        });
    }

    return true;
}

function renderFallbackGroupChart(groups) {
    const maxCount = Math.max(...groups.map((group) => Number(group.count || 0)), 1);

    return `
        <div class="analysis-chart-fallback">
            <p class="analysis-chart-fallback-note">Interactive charts are unavailable right now, so this plain view is shown instead.</p>
            ${groups
                .map((group) => {
                    const count = Number(group.count || 0);
                    const width = Math.max(6, Math.round((count / maxCount) * 100));
                    const percent = typeof group.share === "number" ? Math.round(group.share * 100) : 0;
                    return `
                        <div class="analysis-bar">
                            <div class="analysis-bar-header">
                                <span class="analysis-bar-label">${escapeHtml(group.label)}</span>
                                <span class="analysis-bar-value">${count} responses${percent ? ` | ${percent}%` : ""}</span>
                            </div>
                            <div class="analysis-bar-track">
                                <div class="analysis-bar-fill${group.is_noise ? " analysis-bar-fill-noise" : ""}" style="width:${width}%"></div>
                            </div>
                        </div>
                    `;
                })
                .join("")}
        </div>
    `;
}

function clearAnalysisChart() {
    purgePlotlyCharts(elements.analysisChart);
    elements.analysisChart.hidden = true;
    elements.analysisChart.innerHTML = "";
}

function purgePlotlyCharts(container) {
    const plotly = getPlotly();
    if (!plotly || !(container instanceof HTMLElement)) {
        return;
    }

    container.querySelectorAll(".analysis-plot-surface").forEach((plotSurface) => {
        try {
            plotly.purge(plotSurface);
        } catch (_error) {
            // Ignore Plotly cleanup issues when the chart has already been discarded.
        }
    });
}

function resizeAnalysisPlots() {
    const plotly = getPlotly();
    if (!plotly || elements.analysisChart.hidden) {
        return;
    }

    elements.analysisChart.querySelectorAll(".analysis-plot-surface").forEach((plotSurface) => {
        try {
            plotly.Plots.resize(plotSurface);
        } catch (_error) {
            // Ignore resize failures for charts that are being re-rendered.
        }
    });
}

function queueAnalysisPlotResize() {
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            resizeAnalysisPlots();
        });
    });
}

function getPlotly() {
    return typeof window !== "undefined" && typeof window.Plotly !== "undefined"
        ? window.Plotly
        : null;
}

async function downloadAnalysisReport() {
    if (!state.resultId || !state.analysisResult?.ok || state.analysisExportRunning) {
        return;
    }

    state.analysisExportFormat = normalizeAnalysisExportFormat(state.analysisExportFormat);
    state.analysisExportMenuOpen = false;
    state.analysisExportRunning = true;
    renderAnalysisExportControls();

    try {
        const charts = await captureRenderedAnalysisCharts();
        const response = await fetch(`/analysis-export/${encodeURIComponent(state.resultId)}`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                format: state.analysisExportFormat || "pdf",
                report_title: buildAnalysisExportTitle(),
                source_filename: state.response?.filename || "",
                subtitle: elements.analysisResultsSubtitle?.textContent?.trim() || "",
                active_filters: buildAnalysisExportFilters(),
                charts,
                analysis_result: state.analysisResult,
            }),
        });
        if (response.status === 401) {
            sessionStorage.removeItem(RESULT_STORAGE_KEY);
            window.location.assign("/login");
            return;
        }
        if (response.status === 404) {
            const payload = await parseJson(response);
            handleMissingResultState(payload.detail || "The processed result is no longer available.");
            return;
        }
        if (!response.ok) {
            const payload = await parseJson(response);
            throw new Error(payload.detail || "Unable to export the report.");
        }

        const blob = await response.blob();
        const objectUrl = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = objectUrl;
        anchor.download = parseDownloadFilename(response.headers.get("Content-Disposition"))
            || `${buildAnalysisExportFileStem()}.${state.analysisExportFormat || "pdf"}`;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(objectUrl);
        clearAnalysisMessage();
    } catch (error) {
        const message = error instanceof Error ? error.message : "Unable to export the report.";
        renderAnalysisMessage("error", message);
    } finally {
        state.analysisExportRunning = false;
        renderAnalysisExportControls();
    }
}

function normalizeAnalysisExportFormat(value) {
    return value === "docx" || value === "pptx" || value === "pdf"
        ? value
        : "pdf";
}

function displayAnalysisExportFormat(value) {
    switch (normalizeAnalysisExportFormat(value)) {
    case "docx":
        return "Doc";
    case "pptx":
        return "Slides";
    default:
        return "PDF";
    }
}

function buildAnalysisExportTitle() {
    if (!state.analysisResult) {
        return "Verbatim Analysis Report";
    }
    return `${displayColumnLabel(state.analysisResult.text_column_name)} - ${state.analysisResult.model_label} Report`;
}

function buildAnalysisExportFileStem() {
    const sourceName = stripFilenameExtension(state.response?.filename || "verbatim-analysis");
    const methodSlug = slugify(displayAnalysisMode(state.analysisResult?.model_key || state.selectedAnalysisModel));
    return `${slugify(sourceName)}-${methodSlug || "analysis"}-report`;
}

function buildAnalysisExportFilters() {
    return Object.entries(state.activeFilters).map(([columnName, values]) => {
        const definition = getFilterDefinition(columnName);
        return {
            column_name: columnName,
            display_name: displayFilterName(definition) || columnName,
            values: Array.isArray(values) ? values : [],
        };
    });
}

async function captureRenderedAnalysisCharts() {
    const plotly = getPlotly();
    if (!plotly || typeof plotly.toImage !== "function" || !(elements.analysisChart instanceof HTMLElement)) {
        return [];
    }

    const plotSurfaces = Array.from(elements.analysisChart.querySelectorAll(".analysis-plot-surface"));
    if (!plotSurfaces.length) {
        return [];
    }

    const chartDefinitions = buildAnalysisChartDefinitions(plotSurfaces.length);
    const images = await Promise.all(
        plotSurfaces.map(async (plotSurface, index) => {
            if (!(plotSurface instanceof HTMLElement)) {
                return null;
            }
            const rect = plotSurface.getBoundingClientRect();
            const width = Math.max(1200, Math.round(rect.width * 2) || 1200);
            const height = Math.max(720, Math.round(rect.height * 2) || 720);
            try {
                const definition = chartDefinitions[index] || chartDefinitions[0] || {
                    title: `Chart ${index + 1}`,
                    caption: "",
                };
                const imageDataUrl = await captureAnalysisChartImage(plotly, plotSurface, {
                    width,
                    height,
                    definition,
                });
                return {
                    title: definition.title,
                    caption: definition.caption,
                    image_data_url: imageDataUrl,
                };
            } catch (error) {
                console.warn("[Verbatim App] Unable to capture chart image for export.", error);
                return null;
            }
        }),
    );

    return images.filter(Boolean);
}

function buildAnalysisChartDefinitions(surfaceCount) {
    const result = state.analysisResult;
    if (!result) {
        return [];
    }
    const chartCaption = elements.analysisChart?.querySelector(".analysis-chart-caption")?.textContent?.trim() || "";
    const chartTitle = elements.analysisChart?.querySelector(".analysis-chart-title")?.textContent?.trim() || "";

    if (Array.isArray(result.ngram_buckets) && result.ngram_buckets.length) {
        return result.ngram_buckets.slice(0, surfaceCount).map((bucket) => ({
            title: bucket.label || `${bucket.ngram_size}-grams`,
            caption: chartCaption,
            kind: "ngram",
            ngramSize: Number(bucket.ngram_size || 0),
        }));
    }

    if (result.model_key === "kmeans") {
        return [
            {
                title: "Response map",
                caption: "Spatial view of the clustered responses currently shown on screen.",
                kind: "scatter",
            },
        ];
    }

    return [
        {
            title: chartTitle || `${displayAnalysisMode(result.model_key)} distribution`,
            caption: chartCaption,
            kind: "group",
        },
    ];
}

async function captureAnalysisChartImage(plotly, plotSurface, { width, height, definition }) {
    const baseLayout = clonePlotlyFigureValue(plotSurface.layout) || {};
    const exportOverrides = buildAnalysisExportLayoutOverrides(definition, baseLayout);
    if (!Object.keys(exportOverrides).length) {
        return plotly.toImage(plotSurface, {
            format: "png",
            width,
            height,
        });
    }

    const exportContainer = document.createElement("div");
    exportContainer.style.position = "fixed";
    exportContainer.style.left = "-10000px";
    exportContainer.style.top = "0";
    exportContainer.style.pointerEvents = "none";
    exportContainer.style.width = `${width}px`;
    exportContainer.style.height = `${height}px`;
    document.body.appendChild(exportContainer);

    try {
        const data = clonePlotlyFigureValue(plotSurface.data) || [];
        const layout = {
            ...baseLayout,
            ...exportOverrides,
            width,
            height,
        };
        const config = {
            displaylogo: false,
            responsive: false,
            modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d"],
            staticPlot: true,
        };
        await plotly.newPlot(exportContainer, data, layout, config);
        return await plotly.toImage(exportContainer, {
            format: "png",
            width,
            height,
        });
    } finally {
        if (typeof plotly.purge === "function") {
            plotly.purge(exportContainer);
        }
        exportContainer.remove();
    }
}

function buildAnalysisExportLayoutOverrides(definition, baseLayout) {
    const kind = definition?.kind || "";
    const ngramSize = Number(definition?.ngramSize || 0);
    const baseMargin = baseLayout?.margin || {};
    const baseFont = baseLayout?.font || {};
    const baseXAxis = baseLayout?.xaxis || {};
    const baseYAxis = baseLayout?.yaxis || {};

    const overrides = {
        paper_bgcolor: "#fffaf2",
    };

    if (kind === "ngram") {
        overrides.margin = {
            ...baseMargin,
            l: Math.max(Number(baseMargin.l || 0), 240),
            r: Math.max(Number(baseMargin.r || 0), 18),
            t: Math.max(Number(baseMargin.t || 0), 34),
            b: Math.max(Number(baseMargin.b || 0), 42),
        };
        overrides.font = {
            ...baseFont,
            size: Math.max(Number(baseFont.size || 0), 11),
        };
        overrides.xaxis = {
            ...baseXAxis,
            tickfont: {
                ...(baseXAxis.tickfont || {}),
                size: Math.max(Number(baseXAxis?.tickfont?.size || 0), 11),
            },
        };
        overrides.yaxis = {
            ...baseYAxis,
            automargin: true,
            tickfont: {
                ...(baseYAxis.tickfont || {}),
                size: Math.max(Number(baseYAxis?.tickfont?.size || 0), ngramSize === 3 ? 17 : 24),
            },
        };
    }

    if (kind === "group") {
        overrides.margin = {
            ...baseMargin,
            l: Math.max(Number(baseMargin.l || 0), 160),
        };
        overrides.yaxis = {
            ...baseYAxis,
            automargin: true,
            tickfont: {
                ...(baseYAxis.tickfont || {}),
                size: Math.max(Number(baseYAxis?.tickfont?.size || 0), 11),
            },
        };
    }

    return overrides;
}

function clonePlotlyFigureValue(value) {
    if (value === null || value === undefined) {
        return value;
    }
    return JSON.parse(JSON.stringify(value));
}

function parseDownloadFilename(contentDisposition) {
    if (!contentDisposition) {
        return "";
    }
    const match = contentDisposition.match(/filename=\"?([^\";]+)\"?/i);
    return match ? match[1] : "";
}

function buildPercentLabel(share) {
    if (typeof share !== "number" || Number.isNaN(share)) {
        return "Not available";
    }
    return `${Math.round(share * 100)}%`;
}

function buildExampleRowLabel(examples) {
    if (!Array.isArray(examples) || !examples.length) {
        return "No representative rows";
    }

    const labels = examples
        .map((example) => Number(example.row_number || 0))
        .filter((rowNumber) => rowNumber > 0)
        .map((rowNumber) => `Row ${rowNumber}`);

    return labels.length ? labels.join(", ") : "No representative rows";
}

function wrapPlotLabel(value, maxLineLength = 28) {
    const words = normalizeValue(value).split(/\s+/).filter(Boolean);
    if (!words.length) {
        return "Untitled";
    }

    const lines = [];
    let currentLine = "";
    words.forEach((word) => {
        const nextValue = currentLine ? `${currentLine} ${word}` : word;
        if (nextValue.length <= maxLineLength || !currentLine) {
            currentLine = nextValue;
            return;
        }
        lines.push(currentLine);
        currentLine = word;
    });

    if (currentLine) {
        lines.push(currentLine);
    }

    return lines.join("<br>");
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

function summaryMetric(kind, label, value) {
    return `
        <div class="dashboard-metric">
            <div class="dashboard-metric-top">
                <span class="dashboard-metric-icon" aria-hidden="true">${dashboardMetricIcon(kind)}</span>
                <span class="dashboard-metric-value">${escapeHtml(value)}</span>
            </div>
            <span class="dashboard-metric-label">${escapeHtml(label)}</span>
        </div>
    `;
}

function dashboardMetricIcon(kind) {
    const icons = {
        rows: `
            <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
                <rect x="3" y="5" width="18" height="16" rx="2"></rect>
                <path d="M3 10.5h18M8.5 10.5V21M15.5 10.5V21"></path>
                <path d="M3 15.75h18"></path>
                <path d="M7 3.5h10"></path>
            </svg>
        `,
        columns: `
            <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
                <rect x="3" y="5" width="18" height="14" rx="2"></rect>
                <path d="M9 5v14M15 5v14"></path>
                <path d="M3 10h18M3 14h18"></path>
            </svg>
        `,
        verbatim: `
            <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
                <path d="M6 5h12a3 3 0 0 1 3 3v6a3 3 0 0 1-3 3h-6l-4.5 3V17H6a3 3 0 0 1-3-3V8a3 3 0 0 1 3-3Z"></path>
                <path d="M8 9.5h8M8 12.5h6"></path>
            </svg>
        `,
    };
    return icons[kind] || "";
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

function handleFilterColumnChange(event) {
    const target = event.target;
    if (!(target instanceof HTMLSelectElement)) {
        return;
    }
    state.selectedFilterColumn = target.value;
    const selectedDefinition = getFilterDefinition(state.selectedFilterColumn);
    state.selectedFilterValue = selectedDefinition?.options?.[0]?.value || "";
    renderFilterBar();
}

function handleFilterValueChange(event) {
    const target = event.target;
    if (!(target instanceof HTMLSelectElement)) {
        return;
    }
    state.selectedFilterValue = target.value;
}

async function handleAddFilter() {
    if (!state.selectedFilterColumn || !state.selectedFilterValue) {
        return;
    }

    showFilterModalMessage("neutral", "Applying filter...");
    const nextFilters = {
        ...state.activeFilters,
        [state.selectedFilterColumn]: [state.selectedFilterValue],
    };
    try {
        await applyActiveFilters(nextFilters);
        closeFilterModal();
    } catch (error) {
        const message = error instanceof Error ? error.message : "Unable to apply the filter.";
        showFilterModalMessage("error", message);
    }
}

async function handleClearFilters() {
    if (!hasActiveFilters()) {
        return;
    }

    try {
        await applyActiveFilters({});
        closeFilterModal();
    } catch (error) {
        const message = error instanceof Error ? error.message : "Unable to clear filters.";
        showFilterModalMessage("error", message);
    }
}

async function removeActiveFilter(columnName) {
    if (!(columnName in state.activeFilters)) {
        return;
    }

    const nextFilters = { ...state.activeFilters };
    delete nextFilters[columnName];
    try {
        await applyActiveFilters(nextFilters);
        closeFilterModal();
    } catch (error) {
        console.error(error);
    }
}

async function applyActiveFilters(nextFilters) {
    state.activeFilters = nextFilters;
    const activeAnalysisRequest = getActiveAnalysisRequest();
    const shouldRerunAnalysis = state.currentWorkspace === "analysis-results"
        && Boolean(activeAnalysisRequest.textColumnName)
        && Boolean(activeAnalysisRequest.modelKey);
    await refreshFilteredDatasets({ suppressAnalysisRender: shouldRerunAnalysis });
    if (shouldRerunAnalysis) {
        await runAnalysis({
            scrollIntoView: false,
            preserveCurrentOutput: true,
            requestedColumn: activeAnalysisRequest.textColumnName,
            requestedModel: activeAnalysisRequest.modelKey,
        });
    }
}

async function handlePreviewModeChange() {
    state.showOnlyVerbatim = Boolean(elements.verbatimToggle.checked);
    state.previewColumnOffset = 0;
    const dataset = currentPreviewDataset();
    await ensureDatasetRowCount(dataset, getInitialVisibleRowTarget(dataset));
    renderPreviewTable(false);
    syncSliderRange();
}

function handleAnalysisColumnChange(event) {
    const target = event.target;
    if (!(target instanceof HTMLSelectElement)) {
        return;
    }
    state.selectedAnalysisColumn = target.value;
    state.analysisResult = null;
    renderAnalysisControls();
    renderAnalysisOutput();
}

function handleAnalysisMethodClick(event) {
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

async function handleRunAnalysis() {
    await runAnalysis({ scrollIntoView: true });
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

function isNearBottom(element) {
    return (element.scrollTop + element.clientHeight) >= (element.scrollHeight - 120);
}

async function maybeLoadMorePreviewRows() {
    const dataset = currentPreviewDataset();
    if (dataset === "analysis") {
        await maybeLoadMoreAnalysisRows();
        return;
    }
    if (!state.transformedHasMore || state.transformedLoading || !isNearBottom(elements.tableWrap)) {
        return;
    }
    await loadMoreRows("transformed");
    renderPreviewTable(true);
}

async function maybeLoadMoreAnalysisRows() {
    if (!state.analysisHasMore || state.analysisLoading || !isNearBottom(elements.tableWrap)) {
        return;
    }

    await loadMoreRows("analysis");
    if (state.showOnlyVerbatim) {
        renderPreviewTable(true);
    }
}

async function loadMoreRows(dataset, limit = getRowPageSize(dataset)) {
    if (dataset === "transformed" && state.transformedLoading) {
        return;
    }
    if (dataset === "analysis" && state.analysisLoading) {
        return;
    }
    if (!state.resultId) {
        if (dataset === "transformed") {
            state.transformedHasMore = false;
        } else {
            state.analysisHasMore = false;
        }
        return;
    }

    const offset = dataset === "transformed" ? state.transformedRows.length : state.analysisRows.length;
    if (dataset === "transformed") {
        state.transformedLoading = true;
        updatePreviewRowStatus();
    } else {
        state.analysisLoading = true;
        updatePreviewRowStatus();
    }

    try {
        const payload = await fetchRowsPage(dataset, offset, limit);

        if (dataset === "transformed") {
            state.transformedRows = state.transformedRows.concat(payload.rows || []);
            state.transformedHasMore = Boolean(payload.has_more);
            state.transformedTotalRows = Number(payload.total_row_count || 0);
            state.transformedUnfilteredTotalRows = Number(payload.unfiltered_row_count || 0);
            if (Array.isArray(payload.column_names) && payload.column_names.length) {
                state.transformedColumnNames = payload.column_names;
            }
        } else {
            state.analysisRows = state.analysisRows.concat(payload.rows || []);
            state.analysisHasMore = Boolean(payload.has_more);
            state.analysisTotalRows = Number(payload.total_row_count || 0);
            state.analysisUnfilteredTotalRows = Number(payload.unfiltered_row_count || 0);
            if (Array.isArray(payload.column_names) && payload.column_names.length) {
                state.analysisColumnNames = payload.column_names;
            }
        }
        updatePreviewRowStatus();
    } catch (error) {
        if (dataset === "transformed") {
            state.transformedHasMore = false;
        } else {
            state.analysisHasMore = false;
        }
        console.error(error);
    } finally {
        if (dataset === "transformed") {
            state.transformedLoading = false;
        } else {
            state.analysisLoading = false;
        }
        updatePreviewRowStatus();
    }
}

async function ensureDatasetRowCount(dataset, targetCount) {
    if (getDatasetLoadedCount(dataset) === 0 && getDatasetHasMore(dataset)) {
        await loadMoreRows(dataset, Math.min(ROW_PAGE_SIZE, targetCount));
    }

    const totalCount = getDatasetTotalCount(dataset);
    const desiredCount = Math.min(targetCount, totalCount);
    while (getDatasetLoadedCount(dataset) < desiredCount && getDatasetHasMore(dataset)) {
        const remaining = desiredCount - getDatasetLoadedCount(dataset);
        await loadMoreRows(dataset, Math.min(ROW_PAGE_SIZE, remaining));
    }
}

async function warmAnalysisRows() {
    if (!state.resultId) {
        return;
    }
    await ensureDatasetRowCount("analysis", INITIAL_VISIBLE_ROW_TARGET);
}

async function refreshFilteredDatasets({ suppressAnalysisRender = false } = {}) {
    if (!state.resultId) {
        renderFilterBar();
        renderPreviewTable(false);
        return;
    }

    resetDatasetRows("transformed");
    resetDatasetRows("analysis");

    try {
        const [transformedPayload, analysisPayload] = await Promise.all([
            fetchRowsPage("transformed", 0, FULL_DATA_INITIAL_VISIBLE_ROW_TARGET),
            fetchRowsPage("analysis", 0, INITIAL_VISIBLE_ROW_TARGET),
        ]);
        applyRowsPayload("transformed", transformedPayload);
        applyRowsPayload("analysis", analysisPayload);
    } catch (error) {
        console.error(error);
    }

    renderFilterBar();
    if (state.currentWorkspace === "data") {
        renderPreviewTable(false);
        syncSliderRange();
    }
    if (state.currentWorkspace === "analysis") {
        renderAnalysisPanel();
    }
    if (state.currentWorkspace === "analysis-results" && !suppressAnalysisRender) {
        renderAnalysisOutput();
    }
}

function getActiveAnalysisRequest() {
    return {
        textColumnName: state.analysisResult?.text_column_name || state.selectedAnalysisColumn || "",
        modelKey: state.analysisResult?.model_key || state.selectedAnalysisModel || "",
    };
}

async function runAnalysis({
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

    closeAnalysisGroupModal();
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
            handleMissingResultState(payload.detail || "The processed result is no longer available.");
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
        updateWorkspaceVisibility();
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
            translated_document_count: 0,
            warnings: [],
            error: message,
            groups: [],
            ngram_buckets: [],
            scatter_points: [],
        };
        state.currentWorkspace = "analysis-results";
        updateWorkspaceVisibility();
        renderAnalysisOutput();
    } finally {
        activeAnalysisAbortController = null;
        state.analysisRunning = false;
        renderAnalysisControls();
    }
}

function getDatasetLoadedCount(dataset) {
    return dataset === "analysis" ? state.analysisRows.length : state.transformedRows.length;
}

function getDatasetHasMore(dataset) {
    return dataset === "analysis" ? state.analysisHasMore : state.transformedHasMore;
}

function getDatasetTotalCount(dataset) {
    return dataset === "analysis" ? state.analysisTotalRows : state.transformedTotalRows;
}

function analysisCard(label, value) {
    return `
        <div class="analysis-card">
            <span class="analysis-card-label">${escapeHtml(label)}</span>
            <span class="analysis-card-value">${value}</span>
        </div>
    `;
}

function formatNumber(value) {
    const numericValue = Number(value || 0);
    return new Intl.NumberFormat("en-GB").format(numericValue);
}

function normalizeValue(value) {
    if (value === null || value === undefined) {
        return "";
    }
    return `${value}`.trim();
}

function formatCell(value) {
    const normalized = normalizeValue(value);
    return normalized ? escapeHtml(normalized) : "<span class=\"empty-cell\">-</span>";
}

function escapeHtml(value) {
    return `${value}`
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll("\"", "&quot;")
        .replaceAll("'", "&#39;");
}

function displayColumnLabel(value) {
    return `${value}`.replace(/__idx_\d+$/i, "");
}

function displayAnalysisMode(modelKey) {
    return ANALYSIS_MODE_OPTIONS.find((option) => option.key === modelKey)?.label || modelKey;
}

function stripFilenameExtension(value) {
    const normalized = `${value || ""}`.trim();
    if (!normalized.includes(".")) {
        return normalized;
    }
    return normalized.replace(/\.[^/.]+$/, "");
}

function slugify(value) {
    return `${value || ""}`
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "");
}

function buildPreviewEmptyMessage() {
    const dataset = currentPreviewDataset();
    const isLoading = dataset === "analysis" ? state.analysisLoading : state.transformedLoading;
    if (isLoading) {
        return dataset === "analysis" ? "Loading verbatim data..." : "Loading processed data...";
    }
    return dataset === "analysis"
        ? "No verbatim data is available for this file."
        : "No processed data is available for this file.";
}

function updatePreviewRowStatus() {
    elements.tableRowStatus.textContent = buildRowStatusText(currentPreviewDataset());
}

function buildRowStatusText(dataset) {
    const loadedCount = dataset === "analysis" ? state.analysisRows.length : state.transformedRows.length;
    const totalCount = dataset === "analysis"
        ? Number(state.analysisTotalRows || 0)
        : Number(state.transformedTotalRows || 0);
    const unfilteredCount = dataset === "analysis"
        ? Number(state.analysisUnfilteredTotalRows || 0)
        : Number(state.transformedUnfilteredTotalRows || 0);
    const isLoading = dataset === "analysis" ? state.analysisLoading : state.transformedLoading;

    if (!totalCount && !loadedCount) {
        if (hasActiveFilters()) {
            return `Loaded 0 of 0 rows | filtered from ${unfilteredCount}`;
        }
        return "Loaded 0 rows";
    }

    let text = `Loaded ${loadedCount} of ${totalCount} rows`;
    if (hasActiveFilters()) {
        text += ` | filtered from ${unfilteredCount}`;
    }
    if (isLoading) {
        text += " | loading more";
    }
    return text;
}

function hasActiveFilters() {
    return Object.keys(state.activeFilters).length > 0;
}

function currentPreviewDataset() {
    return state.showOnlyVerbatim ? "analysis" : "transformed";
}

function getRowPageSize(dataset) {
    return dataset === "transformed" ? FULL_DATA_ROW_PAGE_SIZE : ROW_PAGE_SIZE;
}

function getInitialVisibleRowTarget(dataset) {
    return dataset === "transformed" ? FULL_DATA_INITIAL_VISIBLE_ROW_TARGET : INITIAL_VISIBLE_ROW_TARGET;
}

function getVisiblePreviewColumns(columns, dataset) {
    if (dataset === "analysis") {
        return columns;
    }

    const maxOffset = Math.max(0, columns.length - FULL_DATA_VISIBLE_COLUMN_COUNT);
    const start = Math.min(state.previewColumnOffset, maxOffset);
    state.previewColumnOffset = start;
    return columns.slice(start, start + FULL_DATA_VISIBLE_COLUMN_COUNT);
}

function getFilterDefinition(columnName) {
    return state.availableFilters.find((definition) => definition.column_name === columnName) || null;
}

function displayFilterName(definition) {
    if (!definition) {
        return "";
    }
    return definition.display_name || definition.column_name;
}

function getColumnRole(columnName) {
    if (state.analysisVerbatimColumns.includes(columnName)) {
        return "verbatim";
    }
    if (state.analysisMetadataColumns.includes(columnName)) {
        return "metadata";
    }
    return "not assigned";
}

function pruneInvalidActiveFilters() {
    const allowedColumns = new Set(state.availableFilters.map((definition) => definition.column_name));
    const nextFilters = {};
    Object.entries(state.activeFilters).forEach(([columnName, values]) => {
        if (allowedColumns.has(columnName)) {
            nextFilters[columnName] = values;
        }
    });
    state.activeFilters = nextFilters;
}

function showColumnRoleMessage(kind, message) {
    if (!elements.columnRoleMessage) {
        return;
    }
    elements.columnRoleMessage.hidden = false;
    elements.columnRoleMessage.className = `analysis-message analysis-message-${kind}`;
    elements.columnRoleMessage.textContent = message;
}

function hideColumnRoleMessage() {
    if (!elements.columnRoleMessage) {
        return;
    }
    elements.columnRoleMessage.hidden = true;
    elements.columnRoleMessage.textContent = "";
    elements.columnRoleMessage.className = "analysis-message";
}

function showFilterModalMessage(kind, message) {
    if (!elements.filterModalMessage) {
        return;
    }
    elements.filterModalMessage.hidden = false;
    elements.filterModalMessage.className = `analysis-message analysis-message-${kind}`;
    elements.filterModalMessage.textContent = message;
}

function hideFilterModalMessage() {
    if (!elements.filterModalMessage) {
        return;
    }
    elements.filterModalMessage.hidden = true;
    elements.filterModalMessage.textContent = "";
    elements.filterModalMessage.className = "analysis-message";
}

function showAnalysisGroupModalMessage(kind, message) {
    if (!elements.analysisGroupModalMessage) {
        return;
    }
    elements.analysisGroupModalMessage.hidden = false;
    elements.analysisGroupModalMessage.className = `analysis-message analysis-message-${kind}`;
    elements.analysisGroupModalMessage.textContent = message;
}

function hideAnalysisGroupModalMessage() {
    if (!elements.analysisGroupModalMessage) {
        return;
    }
    elements.analysisGroupModalMessage.hidden = true;
    elements.analysisGroupModalMessage.textContent = "";
    elements.analysisGroupModalMessage.className = "analysis-message";
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

function resetDatasetRows(dataset) {
    if (dataset === "transformed") {
        state.transformedRows = [];
        state.transformedHasMore = false;
        state.transformedLoading = false;
        state.transformedTotalRows = 0;
        return;
    }

    state.analysisRows = [];
    state.analysisHasMore = false;
    state.analysisLoading = false;
    state.analysisTotalRows = 0;
}

function applyRowsPayload(dataset, payload) {
    if (dataset === "transformed") {
        state.transformedRows = Array.isArray(payload.rows) ? payload.rows : [];
        state.transformedHasMore = Boolean(payload.has_more);
        state.transformedTotalRows = Number(payload.total_row_count || 0);
        state.transformedUnfilteredTotalRows = Number(payload.unfiltered_row_count || 0);
        if (Array.isArray(payload.column_names) && payload.column_names.length) {
            state.transformedColumnNames = payload.column_names;
        }
        return;
    }

    state.analysisRows = Array.isArray(payload.rows) ? payload.rows : [];
    state.analysisHasMore = Boolean(payload.has_more);
    state.analysisTotalRows = Number(payload.total_row_count || 0);
    state.analysisUnfilteredTotalRows = Number(payload.unfiltered_row_count || 0);
    if (Array.isArray(payload.column_names) && payload.column_names.length) {
        state.analysisColumnNames = payload.column_names;
    }
}

async function fetchRowsPage(dataset, offset, limit) {
    const query = new URLSearchParams({
        dataset,
        offset: `${offset}`,
        limit: `${limit}`,
    });
    if (hasActiveFilters()) {
        query.set("filters", JSON.stringify(state.activeFilters));
    }

    const response = await fetch(`/result-rows/${encodeURIComponent(state.resultId)}?${query.toString()}`);
    if (response.status === 401) {
        sessionStorage.removeItem(RESULT_STORAGE_KEY);
        window.location.assign("/login");
        throw new Error("Session expired.");
    }
    if (response.status === 404) {
        const payload = await parseJson(response);
        handleMissingResultState(payload.detail || "The processed result is no longer available.");
        throw new Error("The processed result is no longer available.");
    }

    const payload = await parseJson(response);
    if (!response.ok) {
        throw new Error(payload.detail || "Unable to load rows.");
    }
    return payload;
}

async function parseJson(response) {
    try {
        return await response.json();
    } catch {
        return {};
    }
}
})();
