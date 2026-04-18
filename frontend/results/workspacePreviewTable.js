import {
    FULL_DATA_VISIBLE_COLUMN_COUNT,
    elements,
    state,
} from "./shared.js";
import { displayColumnLabel, escapeHtml, formatCell } from "./utils.js";
import {
    buildPreviewEmptyMessage,
    currentPreviewDataset,
    ensureDatasetRowCount,
    getInitialVisibleRowTarget,
    getVisiblePreviewColumns,
    maybeLoadMorePreviewRows,
    updatePreviewRowStatus,
} from "./rows.js";
import { renderFilterBar } from "./workspaceFilterBar.js";

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

function syncSliderToScroll() {
    if (currentPreviewDataset() !== "analysis") {
        elements.tableSlider.value = `${state.previewColumnOffset}`;
        return;
    }
    elements.tableSlider.value = `${Math.round(elements.tableWrap.scrollLeft)}`;
}
