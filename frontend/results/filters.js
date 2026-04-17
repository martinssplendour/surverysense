import { elements, state } from "./shared.js";
import { refreshFilteredDatasets } from "./rows.js";

const callbacks = {
    closeFilterModal: () => {},
    getActiveAnalysisRequest: () => ({ textColumnName: "", modelKey: "" }),
    renderFilterBar: () => {},
    runAnalysis: async () => {},
};

export function configureResultsFilters(nextCallbacks) {
    Object.assign(callbacks, nextCallbacks);
}

export function handleFilterColumnChange(event) {
    const target = event.target;
    if (!(target instanceof HTMLSelectElement)) {
        return;
    }
    state.selectedFilterColumn = target.value;
    const selectedDefinition = getFilterDefinition(state.selectedFilterColumn);
    state.selectedFilterValue = selectedDefinition?.options?.[0]?.value || "";
    callbacks.renderFilterBar();
}

export function handleFilterValueChange(event) {
    const target = event.target;
    if (!(target instanceof HTMLSelectElement)) {
        return;
    }
    state.selectedFilterValue = target.value;
    if (state.selectedFilterColumn && state.selectedFilterValue) {
        void handleAddFilter();
    }
}

export async function handleAddFilter() {
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
        callbacks.closeFilterModal();
    } catch (error) {
        const message = error instanceof Error ? error.message : "Unable to apply the filter.";
        showFilterModalMessage("error", message);
    }
}

export async function handleClearFilters() {
    if (!hasActiveFilters()) {
        return;
    }

    try {
        await applyActiveFilters({});
        callbacks.closeFilterModal();
    } catch (error) {
        const message = error instanceof Error ? error.message : "Unable to clear filters.";
        showFilterModalMessage("error", message);
    }
}

export async function removeActiveFilter(columnName) {
    if (!(columnName in state.activeFilters)) {
        return;
    }

    const nextFilters = { ...state.activeFilters };
    delete nextFilters[columnName];
    try {
        await applyActiveFilters(nextFilters);
        callbacks.closeFilterModal();
    } catch (error) {
        console.error(error);
    }
}

export async function applyActiveFilters(nextFilters) {
    state.activeFilters = nextFilters;
    const activeAnalysisRequest = callbacks.getActiveAnalysisRequest();
    const shouldRerunAnalysis = state.currentWorkspace === "analysis-results"
        && Boolean(activeAnalysisRequest.textColumnName)
        && Boolean(activeAnalysisRequest.modelKey);
    await refreshFilteredDatasets({ suppressAnalysisRender: shouldRerunAnalysis });
    if (shouldRerunAnalysis) {
        await callbacks.runAnalysis({
            scrollIntoView: false,
            preserveCurrentOutput: true,
            requestedColumn: activeAnalysisRequest.textColumnName,
            requestedModel: activeAnalysisRequest.modelKey,
        });
    }
}

export function getFilterDefinition(columnName) {
    return state.availableFilters.find((definition) => definition.column_name === columnName) || null;
}

export function displayFilterName(definition) {
    if (!definition) {
        return "";
    }
    return definition.display_name || definition.column_name;
}

export function getColumnRole(columnName) {
    if (state.analysisVerbatimColumns.includes(columnName)) {
        return "verbatim";
    }
    if (state.analysisMetadataColumns.includes(columnName)) {
        return "metadata";
    }
    return "not assigned";
}

export function pruneInvalidActiveFilters() {
    const allowedColumns = new Set(state.availableFilters.map((definition) => definition.column_name));
    const nextFilters = {};
    Object.entries(state.activeFilters).forEach(([columnName, values]) => {
        if (allowedColumns.has(columnName)) {
            nextFilters[columnName] = values;
        }
    });
    state.activeFilters = nextFilters;
}

export function hasActiveFilters() {
    return Object.keys(state.activeFilters).length > 0;
}

export function showColumnRoleMessage(kind, message) {
    if (!elements.columnRoleMessage) {
        return;
    }
    elements.columnRoleMessage.hidden = false;
    elements.columnRoleMessage.className = `analysis-message analysis-message-${kind}`;
    elements.columnRoleMessage.textContent = message;
}

export function hideColumnRoleMessage() {
    if (!elements.columnRoleMessage) {
        return;
    }
    elements.columnRoleMessage.hidden = true;
    elements.columnRoleMessage.textContent = "";
    elements.columnRoleMessage.className = "analysis-message";
}

export function showFilterModalMessage(kind, message) {
    if (!elements.filterModalMessage) {
        return;
    }
    elements.filterModalMessage.hidden = false;
    elements.filterModalMessage.className = `analysis-message analysis-message-${kind}`;
    elements.filterModalMessage.textContent = message;
}

export function hideFilterModalMessage() {
    if (!elements.filterModalMessage) {
        return;
    }
    elements.filterModalMessage.hidden = true;
    elements.filterModalMessage.textContent = "";
    elements.filterModalMessage.className = "analysis-message";
}

export function showAnalysisGroupModalMessage(kind, message) {
    if (!elements.analysisGroupModalMessage) {
        return;
    }
    elements.analysisGroupModalMessage.hidden = false;
    elements.analysisGroupModalMessage.className = `analysis-message analysis-message-${kind}`;
    elements.analysisGroupModalMessage.textContent = message;
}

export function hideAnalysisGroupModalMessage() {
    if (!elements.analysisGroupModalMessage) {
        return;
    }
    elements.analysisGroupModalMessage.hidden = true;
    elements.analysisGroupModalMessage.textContent = "";
    elements.analysisGroupModalMessage.className = "analysis-message";
}
