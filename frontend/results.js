// Entry-point orchestrator: wires all results sub-modules together and boots the results page runtime.
import { elements } from "./results/shared.js";
import {
    configureResultsFilters,
} from "./results/filters.js";
import {
    configureResultsCharts,
} from "./results/charts.js";
import {
    configureResultsDataExport,
} from "./results/dataExport.js";
import { configureResultsRows, parseJson } from "./results/rows.js";
import {
    clearAnalysisMessage,
    configureResultsAnalysis,
    getActiveAnalysisRequest,
    runAnalysis,
    renderAnalysisExportControls,
    renderAnalysisMessage,
    renderAnalysisOutput,
    renderAnalysisPanel,
} from "./results/analysis.js";
import {
    closeAnalysisGroupModal,
    openAnalysisGroupModalByIndex,
    openAnalysisNgramModal,
} from "./results/modals.js";
import {
    configureResultsColumnRoles,
} from "./results/columnRoles.js";
import {
    closeFilterModal,
    handleMissingResultState,
    loadResultsPage,
    persistCurrentPayload,
    renderDashboard,
    renderFilterBar,
    renderPreviewTable,
    syncSliderRange,
    updateWorkspaceVisibility,
} from "./results/workspace.js";
import { bindResultsEvents } from "./results/resultsEventBindings.js";

(function () {
    configureResultsCharts({
        clearAnalysisMessage,
        handleMissingResultState,
        openAnalysisGroupModalByIndex,
        openAnalysisNgramModal,
        parseJson,
        renderAnalysisExportControls,
        renderAnalysisMessage,
    });
    configureResultsDataExport({
        handleMissingResultState,
        parseJson,
    });
    configureResultsRows({
        handleMissingResultState,
        renderAnalysisOutput,
        renderAnalysisPanel,
        renderFilterBar,
        renderPreviewTable,
        syncSliderRange,
    });
    configureResultsFilters({
        closeFilterModal,
        getActiveAnalysisRequest,
        renderFilterBar,
        runAnalysis,
    });
    configureResultsAnalysis({
        closeAnalysisGroupModal,
        handleMissingResultState,
        renderFilterBar,
        updateWorkspaceVisibility,
    });
    configureResultsColumnRoles({
        handleMissingResultState,
        persistCurrentPayload,
        renderDashboard,
    });

    // Guard against running on pages that don't include the results markup (e.g. the upload-only layout).
    if (elements.dashboardPanel && elements.openAnalysisButton && elements.openDataButton) {
        bindResultsEvents();
        void loadResultsPage();
    }
})();
