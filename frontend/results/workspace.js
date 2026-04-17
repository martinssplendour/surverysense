import {
    FULL_DATA_VISIBLE_COLUMN_COUNT,
    RESULT_STORAGE_KEY,
    elements,
    state,
} from "./shared.js";
import { displayColumnLabel, escapeHtml, formatCell, formatNumber, summaryMetric } from "./utils.js";
import { displayFilterName, getFilterDefinition, hideFilterModalMessage } from "./filters.js";
import {
    buildPreviewEmptyMessage,
    currentPreviewDataset,
    ensureDatasetRowCount,
    getInitialVisibleRowTarget,
    getVisiblePreviewColumns,
    hasActiveFilters,
    maybeLoadMorePreviewRows,
    updatePreviewRowStatus,
} from "./rows.js";
import { renderAnalysisOutput, renderAnalysisPanel } from "./analysis.js";
import { closeAnalysisGroupModal } from "./modals.js";
import { closeColumnRoleModal } from "./columnRoles.js";

export async function loadResultsPage() {
    const queryHandoff = isUploadHandoffNavigation();
    if (isPageReload() && !queryHandoff) {
        sessionStorage.removeItem(RESULT_STORAGE_KEY);
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
            : "No verbatim columns detected — use Edit Columns to assign them.";
    }
}

export async function openWorkspace(nextWorkspace) {
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

export function renderFilterBar() {
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

export function openFilterModal() {
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

export function closeFilterModal() {
    if (!elements.filterModal) {
        return;
    }
    elements.filterModal.hidden = true;
    hideFilterModalMessage();
}

export function handleDocumentKeydown(event) {
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

export function renderPreviewTable(preserveScroll) {
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

export function handleSliderInput(event) {
    if (currentPreviewDataset() === "analysis") {
        elements.tableWrap.scrollLeft = Number(event.target.value);
        return;
    }

    state.previewColumnOffset = Number(event.target.value);
    renderPreviewTable(true);
}

export function handlePreviewTableScroll() {
    if (currentPreviewDataset() === "analysis") {
        syncSliderToScroll();
    }
    void maybeLoadMorePreviewRows();
}

export async function handlePreviewModeChange() {
    state.showOnlyVerbatim = Boolean(elements.verbatimToggle.checked);
    state.previewColumnOffset = 0;
    const dataset = currentPreviewDataset();
    await ensureDatasetRowCount(dataset, getInitialVisibleRowTarget(dataset));
    renderPreviewTable(false);
    syncSliderRange();
}

export function syncSliderRange() {
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

export function persistCurrentPayload() {
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

export function handleMissingResultState(message = "The processed result is no longer available. Upload the file again.") {
    console.warn(`[Verbatim App] ${message}`);
    resetToUploadState();
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

function syncSliderToScroll() {
    if (currentPreviewDataset() !== "analysis") {
        elements.tableSlider.value = `${state.previewColumnOffset}`;
        return;
    }
    elements.tableSlider.value = `${Math.round(elements.tableWrap.scrollLeft)}`;
}
