import { RESULT_STORAGE_KEY, elements, state } from "./shared.js";
import { parseDownloadFilename, slugify, stripFilenameExtension } from "./shared/utils.js";

const callbacks = {
    handleMissingResultState: () => {},
    parseJson: async () => ({}),
};

export function configureResultsDataExport(nextCallbacks) {
    Object.assign(callbacks, nextCallbacks);
}

export function normalizeDataExportScope(value) {
    return value === "verbatim_only" ? "verbatim_only" : "clean_data";
}

export function clearDataExportMessage() {
    if (!elements.dataExportMessage) {
        return;
    }
    elements.dataExportMessage.hidden = true;
    elements.dataExportMessage.textContent = "";
    elements.dataExportMessage.className = "analysis-message";
}

export function renderDataExportControls() {
    const hasCleanData = Boolean(state.resultId && state.transformedColumnNames.length);
    const hasVerbatimColumns = state.analysisVerbatimColumns.length > 0;
    if (!hasCleanData || state.dataExportRunning || state.currentWorkspace !== "data") {
        state.dataExportMenuOpen = false;
    }
    const isMenuOpen = hasCleanData
        && !state.dataExportRunning
        && state.currentWorkspace === "data"
        && Boolean(state.dataExportMenuOpen);

    if (elements.dataExportToggleButton) {
        elements.dataExportToggleButton.disabled = !hasCleanData || state.dataExportRunning;
        elements.dataExportToggleButton.setAttribute("aria-expanded", isMenuOpen ? "true" : "false");
        elements.dataExportToggleButton.title = state.dataExportRunning
            ? "Preparing cleaned data download"
            : "Download cleaned data";
    }

    if (elements.dataExportMenu) {
        elements.dataExportMenu.hidden = !isMenuOpen;
        const items = elements.dataExportMenu.querySelectorAll("[data-data-export-scope]");
        items.forEach((item) => {
            if (!(item instanceof HTMLButtonElement)) {
                return;
            }
            const scope = normalizeDataExportScope(item.dataset.dataExportScope);
            const isDisabled = state.dataExportRunning || (scope === "verbatim_only" && !hasVerbatimColumns);
            item.disabled = isDisabled;
            item.tabIndex = isMenuOpen && !isDisabled ? 0 : -1;
        });
    }
}

export async function downloadDataExport(scopeValue) {
    const scope = normalizeDataExportScope(scopeValue);
    if (!state.resultId || state.dataExportRunning) {
        return;
    }
    if (scope === "verbatim_only" && !state.analysisVerbatimColumns.length) {
        renderDataExportMessage("error", "No verbatim columns are available to download.");
        return;
    }

    clearDataExportMessage();
    state.dataExportMenuOpen = false;
    state.dataExportRunning = true;
    renderDataExportControls();

    try {
        const query = new URLSearchParams({
            scope,
            source_filename: state.response?.filename || "",
        });
        if (Object.keys(state.activeFilters).length) {
            query.set("filters", JSON.stringify(state.activeFilters));
        }
        const response = await fetch(`/result-export/${encodeURIComponent(state.resultId)}?${query.toString()}`);
        if (response.status === 401) {
            sessionStorage.removeItem(RESULT_STORAGE_KEY);
            window.location.assign("/login");
            return;
        }
        if (response.status === 404) {
            const payload = await callbacks.parseJson(response);
            callbacks.handleMissingResultState(payload.detail || "The processed result is no longer available.");
            return;
        }
        if (!response.ok) {
            const payload = await callbacks.parseJson(response);
            throw new Error(payload.detail || "Unable to download the cleaned data.");
        }

        const blob = await response.blob();
        const objectUrl = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = objectUrl;
        anchor.download = parseDownloadFilename(response.headers.get("Content-Disposition"))
            || buildFallbackFilename(scope);
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(objectUrl);
        clearDataExportMessage();
    } catch (error) {
        const message = error instanceof Error ? error.message : "Unable to download the cleaned data.";
        renderDataExportMessage("error", message);
    } finally {
        state.dataExportRunning = false;
        renderDataExportControls();
    }
}

function renderDataExportMessage(kind, message) {
    if (!elements.dataExportMessage) {
        return;
    }
    elements.dataExportMessage.hidden = false;
    elements.dataExportMessage.className = `analysis-message analysis-message-${kind}`;
    elements.dataExportMessage.textContent = message;
}

function buildFallbackFilename(scope) {
    const baseName = slugify(stripFilenameExtension(state.response?.filename || "verbatim-app")) || "verbatim-app";
    const scopeSuffix = scope === "verbatim_only" ? "verbatim-columns" : "clean-data";
    const filteredSuffix = Object.keys(state.activeFilters).length ? "-filtered" : "";
    return `${baseName}-${scopeSuffix}${filteredSuffix}.csv`;
}
