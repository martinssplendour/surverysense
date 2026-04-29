import { elements, setPreviewState, state } from "../shared.js";
import { openWorkspace, resetToUploadState } from "../workspace/workspace.js";

export function bindNavigationEvents() {
    elements.uploadDataButton?.addEventListener("click", resetToUploadState);
    elements.openAnalysisButton?.addEventListener("click", () => {
        void openWorkspace("analysis");
    });
    elements.openDataButton?.addEventListener("click", () => {
        setPreviewState({ dataset: null, showOnlyVerbatim: false });
        void openWorkspace("data");
    });
    elements.dataAnalyseButton?.addEventListener("click", () => {
        void openWorkspace("analysis");
    });
    elements.backToAnalysisResultsDataButton?.addEventListener("click", () => {
        void openWorkspace("analysis-results");
    });
    elements.backToDashboardAnalysisButton?.addEventListener("click", () => {
        void openWorkspace("dashboard");
    });
    elements.backToAnalysisSetupButton?.addEventListener("click", () => {
        void openWorkspace("analysis");
    });
    elements.analysisViewDataButton?.addEventListener("click", () => {
        setPreviewState({
            dataset: state.analysisResult?.model_key && state.analysisResult?.model_key !== "ngrams"
                ? "community_analysis"
                : null,
            showOnlyVerbatim: false,
        });
        void openWorkspace("data");
    });
    elements.analysisEmptyActionButton?.addEventListener("click", () => {
        void openWorkspace("analysis");
    });
    elements.backToDashboardDataButton?.addEventListener("click", () => {
        void openWorkspace("dashboard");
    });
}
