import { elements, setDataExportState, state } from "../shared.js";
import { downloadDataExport, renderDataExportControls } from "../dataExport.js";

export function bindDataExportEvents() {
    elements.dataExportToggleButton?.addEventListener("click", handleDataExportToggleClick);
    elements.dataExportMenu?.addEventListener("click", handleDataExportMenuClick);
    document.addEventListener("click", handleDataExportDocumentClick);
}

function handleDataExportToggleClick(event) {
    event.stopPropagation();
    if (state.dataExportRunning) {
        return;
    }
    setDataExportState({ menuOpen: !state.dataExportMenuOpen });
    renderDataExportControls();
}

function handleDataExportMenuClick(event) {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
        return;
    }
    const scopeButton = target.closest("[data-data-export-scope]");
    if (!(scopeButton instanceof HTMLElement)) {
        return;
    }
    const scope = scopeButton.dataset.dataExportScope;
    setDataExportState({ menuOpen: false });
    renderDataExportControls();
    void downloadDataExport(scope);
}

function handleDataExportDocumentClick(event) {
    const target = event.target;
    if (!(target instanceof Node) || !state.dataExportMenuOpen) {
        return;
    }
    if (!(elements.dataExportMenu?.contains(target) || elements.dataExportToggleButton?.contains(target))) {
        setDataExportState({ menuOpen: false });
        renderDataExportControls();
    }
}
