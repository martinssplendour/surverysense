// Re-export the split workspace modules so existing imports keep working while
// persistence and view orchestration live in smaller files.
export {
    closeFilterModal,
    openFilterModal,
    renderFilterBar,
} from "./workspaceFilterBar.js";
export {
    handleDocumentKeydown,
} from "./workspaceModalFocus.js";
export {
    handlePreviewModeChange,
    handlePreviewTableScroll,
    handleSliderInput,
    renderPreviewTable,
    syncSliderRange,
} from "./workspacePreviewTable.js";
export {
    handleMissingResultState,
    loadResultsPage,
    persistCurrentPayload,
    resetToUploadState,
} from "./workspacePersistence.js";
export {
    openWorkspace,
    renderDashboard,
    updateWorkspaceVisibility,
} from "./workspaceView.js";
