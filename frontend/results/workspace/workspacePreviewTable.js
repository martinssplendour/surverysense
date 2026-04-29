import {
    FULL_DATA_VISIBLE_COLUMN_COUNT,
    elements,
    setPreviewState,
    state,
} from "../shared.js";
import { renderDataExportControls } from "../dataExport.js";
import { displayColumnLabel, escapeHtml, formatCell } from "../shared/utils.js";
import {
    buildPreviewEmptyMessage,
    currentPreviewDataset,
    ensureDatasetRowCount,
    getInitialVisibleRowTarget,
    getVisiblePreviewColumns,
    maybeLoadMorePreviewRows,
    updatePreviewRowStatus,
} from "../data/rows.js";
import { renderFilterBar } from "./workspaceFilterBar.js";

export function renderPreviewTable(preserveScroll) {
    renderDataExportControls();
    renderFilterBar();

    const dataset = currentPreviewDataset();
    if (elements.backToAnalysisResultsDataButton) {
        elements.backToAnalysisResultsDataButton.hidden = !(
            dataset === "community_analysis"
            && state.analysisResult?.model_key
            && state.analysisResult?.model_key !== "ngrams"
        );
    }
    if (elements.dataPanelTitle) {
        elements.dataPanelTitle.textContent = dataset === "community_analysis"
            ? "Community Data"
            : "Clean Data";
    }
    const allColumns = dataset === "community_analysis"
        ? state.communityAnalysisColumnNames
        : dataset === "analysis"
            ? state.analysisVerbatimColumns
            : state.transformedColumnNames;
    const previewColumns = getVisiblePreviewColumns(allColumns, dataset);
    const previewRows = dataset === "community_analysis"
        ? state.communityAnalysisRows
        : dataset === "analysis"
            ? state.analysisRows
            : state.transformedRows;
    const scrollTop = preserveScroll ? elements.tableWrap.scrollTop : 0;
    const scrollLeft = preserveScroll && dataset !== "transformed" ? elements.tableWrap.scrollLeft : 0;

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
            if (dataset !== "transformed") {
                elements.tableWrap.scrollLeft = scrollLeft;
            }
        }
        syncSliderRange();
    });
}

export function handleSliderInput(event) {
    if (currentPreviewDataset() !== "transformed") {
        elements.tableWrap.scrollLeft = Number(event.target.value);
        return;
    }

    setPreviewState({ columnOffset: Number(event.target.value) });
    renderPreviewTable(true);
}

export function handlePreviewTableScroll() {
    if (currentPreviewDataset() !== "transformed") {
        syncSliderToScroll();
    }
    void maybeLoadMorePreviewRows();
}

export async function handlePreviewModeChange() {
    setPreviewState({
        dataset: null,
        showOnlyVerbatim: Boolean(elements.verbatimToggle.checked),
        columnOffset: 0,
    });
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

    if (currentPreviewDataset() === "transformed") {
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

function syncSliderToScroll() {
    if (currentPreviewDataset() === "transformed") {
        elements.tableSlider.value = `${state.previewColumnOffset}`;
        return;
    }
    elements.tableSlider.value = `${Math.round(elements.tableWrap.scrollLeft)}`;
}
