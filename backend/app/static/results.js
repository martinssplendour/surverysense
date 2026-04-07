const RESULT_STORAGE_KEY = "verbatim-app:last-upload-result";
const ROW_PAGE_SIZE = 250;
const INITIAL_VISIBLE_ROW_TARGET = 250;

const state = {
    response: null,
    resultId: null,
    analysisMetadataColumns: [],
    analysisVerbatimColumns: [],
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
};

const elements = {
    emptyState: document.getElementById("empty-state"),
    resultsHeader: document.getElementById("results-header"),
    summaryStrip: document.getElementById("summary-strip"),
    filterBar: document.getElementById("filter-bar"),
    filterColumnSelect: document.getElementById("filter-column-select"),
    filterValueSelect: document.getElementById("filter-value-select"),
    addFilterButton: document.getElementById("add-filter-btn"),
    activeFilters: document.getElementById("active-filters"),
    filterActiveNote: document.getElementById("filter-active-note"),
    clearFiltersButton: document.getElementById("clear-filters-btn"),
    tableControls: document.getElementById("table-controls"),
    tableScrollControl: document.getElementById("table-scroll-control"),
    tableRowStatus: document.getElementById("table-row-status"),
    previewToggle: document.getElementById("verbatim-only-toggle"),
    tableSlider: document.getElementById("table-slider"),
    tableEmpty: document.getElementById("table-empty"),
    tableWrap: document.getElementById("table-wrap"),
    previewTable: document.getElementById("preview-table"),
    analyzeButton: document.getElementById("analyze-btn"),
    analysisPanel: document.getElementById("analysis-panel"),
    analysisSummary: document.getElementById("analysis-summary"),
    analysisList: document.getElementById("analysis-list"),
    analysisRowStatus: document.getElementById("analysis-row-status"),
    analysisTableEmpty: document.getElementById("analysis-table-empty"),
    analysisTableWrap: document.getElementById("analysis-table-wrap"),
    analysisPreviewTable: document.getElementById("analysis-preview-table"),
    resetButton: document.getElementById("reset-btn"),
    detailsPanel: document.getElementById("details-panel"),
    detailFilename: document.getElementById("detail-filename"),
    detailEncoding: document.getElementById("detail-encoding"),
    detailRawRows: document.getElementById("detail-raw-rows"),
    detailRawColumns: document.getElementById("detail-raw-columns"),
    detailSampleRows: document.getElementById("detail-sample-rows"),
    detailArchitectRows: document.getElementById("detail-architect-rows"),
    manifestPreview: document.getElementById("manifest-preview"),
};

bindEvents();
loadResultsPage();

function bindEvents() {
    elements.resetButton.addEventListener("click", () => {
        sessionStorage.removeItem(RESULT_STORAGE_KEY);
        window.location.assign("/");
    });

    elements.analyzeButton.addEventListener("click", renderAnalysis);
    elements.previewToggle.addEventListener("change", handlePreviewToggle);
    elements.tableSlider.addEventListener("input", handleSliderInput);
    elements.tableWrap.addEventListener("scroll", handlePreviewTableScroll);
    elements.analysisTableWrap.addEventListener("scroll", handleAnalysisTableScroll);
    elements.filterColumnSelect.addEventListener("change", handleFilterColumnChange);
    elements.filterValueSelect.addEventListener("change", handleFilterValueChange);
    elements.addFilterButton.addEventListener("click", handleAddFilter);
    elements.activeFilters.addEventListener("click", handleRemoveFilter);
    elements.clearFiltersButton.addEventListener("click", clearAllFilters);
    window.addEventListener("resize", syncSliderRange);
}

async function loadResultsPage() {
    const payload = readStoredPayload();
    if (!payload) {
        showEmptyState();
        return;
    }

    state.response = payload;
    state.resultId = typeof payload.result_id === "string" ? payload.result_id : null;
    state.analysisMetadataColumns = Array.isArray(payload.analysis_metadata_column_names)
        ? payload.analysis_metadata_column_names
        : [];
    state.analysisVerbatimColumns = Array.isArray(payload.analysis_verbatim_column_names)
        ? payload.analysis_verbatim_column_names
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

    renderResults(payload);
    await warmInitialRows();
}

function readStoredPayload() {
    const raw = sessionStorage.getItem(RESULT_STORAGE_KEY);
    if (!raw) {
        return null;
    }

    try {
        const parsed = JSON.parse(raw);
        if (!parsed || !Array.isArray(parsed.transformed_column_names)) {
            return null;
        }
        return parsed;
    } catch {
        return null;
    }
}

function showEmptyState() {
    elements.emptyState.hidden = false;
    elements.resultsHeader.hidden = true;
    elements.summaryStrip.hidden = true;
    elements.filterBar.hidden = true;
    elements.activeFilters.hidden = true;
    elements.filterActiveNote.hidden = true;
    elements.tableControls.hidden = true;
    elements.tableRowStatus.textContent = "";
    elements.previewToggle.checked = false;
    elements.tableEmpty.hidden = true;
    elements.tableWrap.hidden = true;
    elements.analyzeButton.disabled = true;
    elements.detailsPanel.hidden = true;
}

function renderResults(payload) {
    const layout = payload.manifest?.layout_state || "Unknown";

    elements.emptyState.hidden = true;
    elements.resultsHeader.hidden = false;
    elements.summaryStrip.hidden = false;
    elements.detailsPanel.hidden = false;
    elements.analysisPanel.hidden = true;
    elements.analysisSummary.innerHTML = "";
    elements.analysisList.innerHTML = "";
    elements.analysisPreviewTable.innerHTML = "";
    elements.analysisTableWrap.hidden = true;
    elements.analysisTableEmpty.hidden = true;
    elements.analyzeButton.disabled = false;
    elements.analyzeButton.textContent = "Analyze Verbatim Columns";
    state.showOnlyVerbatim = false;
    elements.previewToggle.checked = false;

    renderSummaryStrip(payload, layout);
    renderFilterBar();
    renderPreviewTable(false);
    renderApiDetails(payload);
}

function renderSummaryStrip(payload, layout) {
    const chips = [
        chip("File", escapeHtml(payload.filename)),
        chip("Layout", `<span class="layout-badge">${escapeHtml(layout)}</span>`),
        chip("Rows", `${payload.transformed_row_count}`),
        chip("Verbatim Columns", `${state.analysisVerbatimColumns.length}`),
    ];
    elements.summaryStrip.innerHTML = chips.join("");
}

function renderFilterBar() {
    if (!state.availableFilters.length) {
        elements.filterBar.hidden = true;
        elements.activeFilters.hidden = true;
        elements.filterActiveNote.hidden = true;
        return;
    }

    const selectedColumnName = state.selectedFilterColumn || "";
    const selectedFilter = state.availableFilters.find((filter) => filter.column_name === selectedColumnName) || null;
    const availableValues = selectedFilter && Array.isArray(selectedFilter.options) ? selectedFilter.options : [];
    if (
        state.selectedFilterValue
        && !availableValues.some((option) => option.value === state.selectedFilterValue)
    ) {
        state.selectedFilterValue = "";
    }

    elements.filterBar.hidden = false;
    elements.filterColumnSelect.innerHTML = [
        `<option value="">Choose metadata</option>`,
        ...state.availableFilters.map((filter) => {
            const isSelected = filter.column_name === selectedColumnName ? " selected" : "";
            return `<option value="${escapeHtml(filter.column_name)}"${isSelected}>${escapeHtml(displayColumnLabel(filter.display_name || filter.column_name))}</option>`;
        }),
    ].join("");

    if (!selectedFilter) {
        elements.filterValueSelect.innerHTML = '<option value="">Choose metadata first</option>';
        elements.filterValueSelect.disabled = true;
        elements.addFilterButton.disabled = true;
    } else {
        elements.filterValueSelect.disabled = false;
        elements.filterValueSelect.innerHTML = [
            `<option value="">Choose value</option>`,
            ...availableValues.map((option) => {
                const isSelected = option.value === state.selectedFilterValue ? " selected" : "";
                return `<option value="${escapeHtml(option.value)}"${isSelected}>${escapeHtml(option.value)} (${option.count})</option>`;
            }),
        ].join("");
        elements.addFilterButton.disabled = !state.selectedFilterValue;
    }

    renderActiveFilters();
    elements.clearFiltersButton.disabled = !hasActiveFilters();
}

function renderPreviewTable(preserveScroll) {
    const transformedColumns = Array.isArray(state.response?.transformed_column_names)
        ? state.response.transformed_column_names
        : [];
    const hasBasePreview = transformedColumns.length > 0;
    const previewColumns = state.showOnlyVerbatim
        ? state.analysisVerbatimColumns
        : transformedColumns;
    const previewRows = state.showOnlyVerbatim
        ? state.analysisRows
        : state.transformedRows;
    const scrollTop = preserveScroll ? elements.tableWrap.scrollTop : 0;
    const scrollLeft = preserveScroll ? elements.tableWrap.scrollLeft : 0;

    if (!hasBasePreview) {
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
            elements.tableWrap.scrollLeft = scrollLeft;
        }
        syncSliderRange();
    });
}

async function renderAnalysis() {
    if (!state.response) {
        return;
    }

    elements.analysisPanel.hidden = false;
    elements.analyzeButton.textContent = "Refresh Verbatim Analysis";
    renderAnalysisSection(false);
    await warmAnalysisRows();
    if (state.showOnlyVerbatim) {
        renderPreviewTable(true);
    }
    renderAnalysisSection(true);
    elements.analysisPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderAnalysisSection(preserveTableScroll) {
    elements.analysisSummary.innerHTML = [
        analysisCard("Metadata Columns", `${state.analysisMetadataColumns.length}`),
        analysisCard("Verbatim Columns", `${state.analysisVerbatimColumns.length}`),
        analysisCard("Analysis Columns", `${(state.response?.analysis_column_names || []).length}`),
        analysisCard("Analysis Rows", `${state.analysisTotalRows || 0}`),
    ].join("");

    if (!state.analysisVerbatimColumns.length) {
        elements.analysisList.innerHTML = `
            <div class="analysis-item">
                <h4>No verbatim columns detected</h4>
                <p class="analysis-sample">The backend selection service did not identify any verbatim columns in the transformed dataset.</p>
            </div>
        `;
    } else {
        const previewRows = state.analysisRows;
        const itemsHtml = state.analysisVerbatimColumns
            .slice(0, 20)
            .map((column) => `
                <article class="analysis-item">
                    <h4>${escapeHtml(displayColumnLabel(column))}</h4>
                    <div class="analysis-meta">
                        <span>Selected as verbatim</span>
                    </div>
                    <p class="analysis-sample">${escapeHtml(firstPreviewValue(previewRows, column))}</p>
                </article>
            `)
            .join("");

        const overflowNote = state.analysisVerbatimColumns.length > 20
            ? `
                <article class="analysis-item">
                    <h4>Additional columns</h4>
                    <p class="analysis-sample">
                        Showing the first 20 selected verbatim columns.
                        ${state.analysisVerbatimColumns.length - 20} more column${state.analysisVerbatimColumns.length - 20 === 1 ? "" : "s"} are available in the analysis-ready dataset.
                    </p>
                </article>
            `
            : "";

        elements.analysisList.innerHTML = itemsHtml + overflowNote;
    }

    renderAnalysisPreviewTable(preserveTableScroll);
}

function renderApiDetails(payload) {
    elements.detailFilename.textContent = payload.filename;
    elements.detailEncoding.textContent = payload.encoding;
    elements.detailRawRows.textContent = `${payload.raw_row_count}`;
    elements.detailRawColumns.textContent = `${payload.raw_column_count}`;
    elements.detailSampleRows.textContent = `${payload.sample_row_count}`;
    elements.detailArchitectRows.textContent = `${payload.architect_row_count}`;
    elements.manifestPreview.textContent = JSON.stringify(payload.manifest, null, 2);
}

function chip(label, value) {
    return `
        <div class="summary-chip">
            <span class="summary-label">${escapeHtml(label)}</span>
            <span class="summary-value">${value}</span>
        </div>
    `;
}

function handleSliderInput(event) {
    elements.tableWrap.scrollLeft = Number(event.target.value);
}

function handlePreviewTableScroll() {
    syncSliderToScroll();
    void maybeLoadMorePreviewRows();
}

function handleAnalysisTableScroll() {
    void maybeLoadMoreAnalysisRows();
}

function handlePreviewToggle(event) {
    state.showOnlyVerbatim = event.target.checked;
    elements.tableWrap.scrollLeft = 0;
    elements.tableWrap.scrollTop = 0;
    elements.tableSlider.value = "0";
    renderPreviewTable(false);
    if (state.showOnlyVerbatim) {
        void warmAnalysisRows().then(() => {
            if (state.showOnlyVerbatim) {
                renderPreviewTable(true);
            }
        });
    }
}

async function handleFilterColumnChange(event) {
    const target = event.target;
    if (!(target instanceof HTMLSelectElement)) {
        return;
    }

    state.selectedFilterColumn = target.value;
    state.selectedFilterValue = state.selectedFilterColumn
        ? (state.activeFilters[state.selectedFilterColumn]?.[0] || "")
        : "";
    renderFilterBar();
}

function handleFilterValueChange(event) {
    const target = event.target;
    if (!(target instanceof HTMLSelectElement)) {
        return;
    }

    state.selectedFilterValue = target.value;
    renderFilterBar();
}

async function handleAddFilter() {
    if (!state.selectedFilterColumn || !state.selectedFilterValue) {
        return;
    }

    state.activeFilters[state.selectedFilterColumn] = [state.selectedFilterValue];
    state.selectedFilterColumn = "";
    state.selectedFilterValue = "";
    renderFilterBar();
    await reloadRowsForActiveFilters();
}

async function handleRemoveFilter(event) {
    const target = event.target;
    if (!(target instanceof Element)) {
        return;
    }

    const button = target.closest("button[data-filter-column]");
    if (!(button instanceof HTMLButtonElement)) {
        return;
    }

    const columnName = button.dataset.filterColumn;
    if (!columnName || !state.activeFilters[columnName]) {
        return;
    }

    delete state.activeFilters[columnName];
    if (state.selectedFilterColumn === columnName) {
        state.selectedFilterColumn = "";
        state.selectedFilterValue = "";
    }
    renderFilterBar();
    await reloadRowsForActiveFilters();
}

async function clearAllFilters() {
    if (!hasActiveFilters()) {
        state.selectedFilterColumn = "";
        state.selectedFilterValue = "";
        renderFilterBar();
        return;
    }

    state.selectedFilterColumn = "";
    state.selectedFilterValue = "";
    state.activeFilters = {};
    renderFilterBar();
    await reloadRowsForActiveFilters();
}

function syncSliderToScroll() {
    elements.tableSlider.value = `${Math.round(elements.tableWrap.scrollLeft)}`;
}

function syncSliderRange() {
    if (elements.tableWrap.hidden) {
        elements.tableControls.hidden = true;
        return;
    }

    const maxScroll = Math.max(0, elements.tableWrap.scrollWidth - elements.tableWrap.clientWidth);
    elements.tableSlider.max = `${Math.round(maxScroll)}`;
    elements.tableSlider.value = `${Math.min(Math.round(elements.tableWrap.scrollLeft), Math.round(maxScroll))}`;
    elements.tableScrollControl.hidden = maxScroll <= 0;
}

function isNearBottom(element) {
    return (element.scrollTop + element.clientHeight) >= (element.scrollHeight - 120);
}

async function maybeLoadMorePreviewRows() {
    const dataset = state.showOnlyVerbatim ? "analysis" : "transformed";
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
    if (!state.analysisHasMore || state.analysisLoading) {
        return;
    }

    const shouldLoadForPreview = state.showOnlyVerbatim && !elements.tableWrap.hidden && isNearBottom(elements.tableWrap);
    const shouldLoadForAnalysisPanel = !elements.analysisTableWrap.hidden && isNearBottom(elements.analysisTableWrap);
    if (!shouldLoadForPreview && !shouldLoadForAnalysisPanel) {
        return;
    }

    await loadMoreRows("analysis");
    if (state.showOnlyVerbatim) {
        renderPreviewTable(true);
    }
    if (!elements.analysisTableWrap.hidden) {
        renderAnalysisSection(true);
    }
}

async function loadMoreRows(dataset, limit = ROW_PAGE_SIZE) {
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
    const query = new URLSearchParams({
        dataset,
        offset: `${offset}`,
        limit: `${limit}`,
    });
    if (hasActiveFilters()) {
        query.set("filters", JSON.stringify(state.activeFilters));
    }

    if (dataset === "transformed") {
        state.transformedLoading = true;
        updatePreviewRowStatus();
    } else {
        state.analysisLoading = true;
        updatePreviewRowStatus();
        updateAnalysisRowStatus();
    }

    try {
        const response = await fetch(`/result-rows/${encodeURIComponent(state.resultId)}?${query.toString()}`);
        if (response.status === 401) {
            sessionStorage.removeItem(RESULT_STORAGE_KEY);
            window.location.assign("/login");
            return;
        }
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.detail || "Unable to load additional rows.");
        }

        if (dataset === "transformed") {
            state.transformedRows = state.transformedRows.concat(payload.rows || []);
            state.transformedHasMore = Boolean(payload.has_more);
            state.transformedTotalRows = Number(payload.total_row_count || 0);
            state.transformedUnfilteredTotalRows = Number(payload.unfiltered_row_count || 0);
            updatePreviewRowStatus();
        } else {
            state.analysisRows = state.analysisRows.concat(payload.rows || []);
            state.analysisHasMore = Boolean(payload.has_more);
            state.analysisTotalRows = Number(payload.total_row_count || 0);
            state.analysisUnfilteredTotalRows = Number(payload.unfiltered_row_count || 0);
            updatePreviewRowStatus();
            updateAnalysisRowStatus();
        }
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
            updatePreviewRowStatus();
        } else {
            state.analysisLoading = false;
            updatePreviewRowStatus();
            updateAnalysisRowStatus();
        }
    }
}

async function warmInitialRows() {
    if (!state.resultId) {
        return;
    }

    await ensureDatasetRowCount("transformed", INITIAL_VISIBLE_ROW_TARGET);
    renderPreviewTable(false);
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

async function reloadRowsForActiveFilters() {
    state.transformedRows = [];
    state.analysisRows = [];
    state.transformedHasMore = true;
    state.analysisHasMore = true;
    state.transformedLoading = false;
    state.analysisLoading = false;
    state.transformedTotalRows = hasActiveFilters() ? 0 : Number(state.response?.transformed_row_count || 0);
    state.analysisTotalRows = hasActiveFilters() ? 0 : Number(state.response?.analysis_row_count || 0);
    state.transformedUnfilteredTotalRows = Number(state.response?.transformed_row_count || 0);
    state.analysisUnfilteredTotalRows = Number(state.response?.analysis_row_count || 0);

    elements.tableWrap.scrollTop = 0;
    elements.tableWrap.scrollLeft = 0;
    elements.analysisTableWrap.scrollTop = 0;
    elements.analysisTableWrap.scrollLeft = 0;
    elements.tableSlider.value = "0";

    renderPreviewTable(false);
    renderAnalysisPreviewTable(false);

    await ensureDatasetRowCount("transformed", INITIAL_VISIBLE_ROW_TARGET);
    renderPreviewTable(false);

    if (state.showOnlyVerbatim || !elements.analysisPanel.hidden) {
        await warmAnalysisRows();
        if (state.showOnlyVerbatim) {
            renderPreviewTable(false);
        }
        if (!elements.analysisPanel.hidden) {
            renderAnalysisSection(false);
        }
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

function firstPreviewValue(rows, column) {
    for (const row of rows) {
        const normalized = normalizeValue(row[column]);
        if (normalized) {
            return normalized;
        }
    }
    return "No non-empty preview value returned for this column.";
}

function renderAnalysisPreviewTable(preserveScroll) {
    const analysisColumns = Array.isArray(state.response?.analysis_column_names)
        ? state.response.analysis_column_names
        : [];
    const scrollTop = preserveScroll ? elements.analysisTableWrap.scrollTop : 0;
    const scrollLeft = preserveScroll ? elements.analysisTableWrap.scrollLeft : 0;
    const resolvedRows = state.analysisRows;

    if (!resolvedRows.length || !analysisColumns.length) {
        updateAnalysisRowStatus();
        elements.analysisTableEmpty.hidden = false;
        elements.analysisTableWrap.hidden = true;
        elements.analysisPreviewTable.innerHTML = "";
        return;
    }

    updateAnalysisRowStatus();

    const head = [
        '<th scope="col" class="row-number-header">Row</th>',
        ...analysisColumns.map((column) => `<th scope="col">${escapeHtml(displayColumnLabel(column))}</th>`),
    ].join("");

    const body = resolvedRows
        .map((row, index) => {
            const cells = analysisColumns
                .map((column) => `<td>${formatCell(row[column])}</td>`)
                .join("");
            return `<tr><th scope="row" class="row-number-cell">${index + 1}</th>${cells}</tr>`;
        })
        .join("");

    elements.analysisPreviewTable.innerHTML = `
        <thead>
            <tr>${head}</tr>
        </thead>
        <tbody>${body}</tbody>
    `;
    elements.analysisTableEmpty.hidden = true;
    elements.analysisTableWrap.hidden = false;
    requestAnimationFrame(() => {
        if (preserveScroll) {
            elements.analysisTableWrap.scrollTop = scrollTop;
            elements.analysisTableWrap.scrollLeft = scrollLeft;
        }
    });
}

function buildPreviewEmptyMessage() {
    if (hasActiveFilters()) {
        return state.showOnlyVerbatim
            ? "No rows match the current metadata filters for the selected verbatim columns."
            : "No rows match the current metadata filters.";
    }
    if (state.showOnlyVerbatim) {
        return state.analysisLoading
            ? "Loading verbatim preview rows..."
            : "No selected verbatim columns are available in the preview.";
    }
    return state.transformedLoading
        ? "Loading transformed preview rows..."
        : "The API did not return preview rows for this file.";
}

function updatePreviewRowStatus() {
    const dataset = state.showOnlyVerbatim ? "analysis" : "transformed";
    elements.tableRowStatus.textContent = buildRowStatusText(dataset);
}

function updateAnalysisRowStatus() {
    elements.analysisRowStatus.textContent = buildRowStatusText("analysis");
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

function renderActiveFilters() {
    const filterEntries = Object.entries(state.activeFilters);
    if (!filterEntries.length) {
        elements.activeFilters.hidden = true;
        elements.activeFilters.innerHTML = "";
        elements.filterActiveNote.hidden = true;
        elements.filterActiveNote.textContent = "";
        return;
    }

    elements.activeFilters.hidden = false;
    elements.activeFilters.innerHTML = filterEntries
        .map(([columnName, values]) => {
            const filter = state.availableFilters.find((item) => item.column_name === columnName);
            const label = displayColumnLabel(filter?.display_name || columnName);
            const value = Array.isArray(values) ? values[0] || "" : "";
            return `
                <div class="active-filter-chip">
                    <span class="active-filter-text">${escapeHtml(label)}: ${escapeHtml(value)}</span>
                    <button
                        type="button"
                        class="active-filter-remove"
                        data-filter-column="${escapeHtml(columnName)}"
                        aria-label="Remove ${escapeHtml(label)} filter"
                    >
                        Remove
                    </button>
                </div>
            `;
        })
        .join("");

    elements.filterActiveNote.hidden = false;
    elements.filterActiveNote.textContent = `${filterEntries.length} filter${filterEntries.length === 1 ? "" : "s"} applied`;
}
