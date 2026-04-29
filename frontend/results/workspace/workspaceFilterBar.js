import { elements, setSelectedFilter, state } from "../shared.js";
import { displayFilterName, getFilterDefinition, hideFilterModalMessage } from "../filters.js";
import { escapeHtml, formatNumber } from "../shared/utils.js";
import { hasActiveFilters } from "../data/rows.js";

export function renderFilterBar() {
    if (!elements.filterBar && !elements.analysisResultsFilterBar) {
        return;
    }
    normalizeDataFilterBackToAnalysisButton();

    const filters = Array.isArray(state.availableFilters) ? state.availableFilters : [];
    if (elements.filterBar) {
        elements.filterBar.hidden = filters.length === 0;
    }
    if (elements.analysisResultsFilterBar) {
        elements.analysisResultsFilterBar.hidden = false;
    }
    if (!filters.length) {
        if (elements.openFilterModalButton) {
            elements.openFilterModalButton.disabled = true;
        }
        if (elements.openAnalysisResultsFilterModalButton) {
            elements.openAnalysisResultsFilterModalButton.disabled = true;
        }
        if (elements.activeFilters) {
            elements.activeFilters.hidden = true;
            elements.activeFilters.innerHTML = "";
        }
        if (elements.analysisResultsActiveFilters) {
            elements.analysisResultsActiveFilters.hidden = true;
            elements.analysisResultsActiveFilters.innerHTML = "";
        }
        if (elements.analysisResultsFilterNote) {
            elements.analysisResultsFilterNote.textContent = "No metadata filters are available for this analysis.";
        }
        return;
    }

    if (!state.selectedFilterColumn || !filters.some((definition) => definition.column_name === state.selectedFilterColumn)) {
        setSelectedFilter({ column: filters[0]?.column_name || "", value: state.selectedFilterValue });
    }

    const selectedDefinition = getFilterDefinition(state.selectedFilterColumn);
    const selectedOptions = Array.isArray(selectedDefinition?.options) ? selectedDefinition.options : [];
    if (!state.selectedFilterValue || !selectedOptions.some((option) => option.value === state.selectedFilterValue)) {
        setSelectedFilter({ column: state.selectedFilterColumn, value: selectedOptions[0]?.value || "" });
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

function normalizeDataFilterBackToAnalysisButton() {
    if (!(elements.backToAnalysisResultsDataButton instanceof HTMLButtonElement)) {
        return;
    }
    const filterRow = document.querySelector("#filter-bar .filter-chip-row");
    if (!(filterRow instanceof HTMLElement)) {
        return;
    }
    elements.backToAnalysisResultsDataButton.className = "dashboard-data-link data-back-to-analysis-link";
    elements.backToAnalysisResultsDataButton.innerHTML = 'Back to analysis <span aria-hidden="true">&rarr;</span>';
    if (elements.backToAnalysisResultsDataButton.parentElement !== filterRow) {
        filterRow.appendChild(elements.backToAnalysisResultsDataButton);
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
