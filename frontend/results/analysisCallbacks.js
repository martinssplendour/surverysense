const callbacks = {
    closeAnalysisGroupModal: () => {},
    handleMissingResultState: () => {},
    renderFilterBar: () => {},
    updateWorkspaceVisibility: () => {},
};

export function configureResultsAnalysis(nextCallbacks) {
    Object.assign(callbacks, nextCallbacks);
}

export { callbacks };
