import { elements } from "../shared.js";
import {
    handleAddFilter,
    handleClearFilters,
    handleFilterColumnChange,
    handleFilterValueChange,
    removeActiveFilter,
} from "../filters.js";
import {
    handlePreviewModeChange,
    handlePreviewTableScroll,
    handleSliderInput,
    syncSliderRange,
} from "../workspace/workspace.js";

export function bindFilterTableEvents() {
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
    window.addEventListener("resize", syncSliderRange);
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
