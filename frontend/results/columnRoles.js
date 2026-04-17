import { RESULT_STORAGE_KEY, elements, state } from "./shared.js";
import { displayColumnLabel, escapeHtml } from "./utils.js";
import {
    getColumnRole,
    hideColumnRoleMessage,
    pruneInvalidActiveFilters,
    showColumnRoleMessage,
} from "./filters.js";
import { parseJson, refreshFilteredDatasets } from "./rows.js";

const callbacks = {
    handleMissingResultState: () => {},
    persistCurrentPayload: () => {},
    renderDashboard: () => {},
};

export function configureResultsColumnRoles(nextCallbacks) {
    Object.assign(callbacks, nextCallbacks);
}

export function openColumnRoleModal() {
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

export function closeColumnRoleModal() {
    if (!elements.columnRoleModal) {
        return;
    }
    elements.columnRoleModal.hidden = true;
    hideColumnRoleMessage();
}

export function renderColumnRoleModal() {
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

export function renderColumnRoleSelectionState() {
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

export function handleColumnRoleSearch(event) {
    const target = event.target;
    if (!(target instanceof HTMLInputElement)) {
        return;
    }
    state.columnSearchTerm = target.value;
    renderColumnRoleModal();
}

export async function applyColumnRoleChange() {
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
            callbacks.handleMissingResultState(payload.detail || "The processed result is no longer available.");
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
        callbacks.persistCurrentPayload();
        callbacks.renderDashboard(state.response || {});
        renderColumnRoleModal();
        showColumnRoleMessage("success", "Column assignment updated.");
    } catch (error) {
        const message = error instanceof Error ? error.message : "Unable to update the column assignment.";
        showColumnRoleMessage("error", message);
    } finally {
        renderColumnRoleSelectionState();
    }
}
