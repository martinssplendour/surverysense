// Builds and manages Plotly charts for community distribution and n-gram frequency.
import { elements, state } from "./shared.js";
import { configureChartExport } from "./charts/export.js";
import { renderCommunityNetworkChart } from "./communityNetworkChartRenderer.js";
import { renderGroupDistributionChart } from "./groupChartRenderer.js";
import { renderNgramFrequencyCharts } from "./ngramChartRenderer.js";
import { purgePlotlyCharts, resizeAnalysisPlots } from "./plotlyRuntime.js";


const callbacks = {
    openAnalysisGroupModalByIndex: () => {},
    openAnalysisNgramModal: () => {},
};


export function configureResultsCharts({
    openAnalysisGroupModalByIndex,
    openAnalysisNgramModal,
    ...chartExportCallbacks
} = {}) {
    if (typeof openAnalysisGroupModalByIndex === "function") {
        callbacks.openAnalysisGroupModalByIndex = openAnalysisGroupModalByIndex;
    }
    if (typeof openAnalysisNgramModal === "function") {
        callbacks.openAnalysisNgramModal = openAnalysisNgramModal;
    }
    configureChartExport(chartExportCallbacks);
}


export function renderAnalysisChart(groups, plotPoints = [], networkEdges = []) {
    if (!groups.length) {
        clearAnalysisChart();
        return;
    }

    const modelKey = state.analysisResult?.model_key || state.selectedAnalysisModel;
    const isCommunityView = modelKey === "community";
    const hasNetworkPlot = isCommunityView && Array.isArray(plotPoints) && plotPoints.length > 0;
    const activeView = hasNetworkPlot && state.communityChartView === "network" ? "network" : "bar";
    const controlsHtml = isCommunityView ? buildCommunityChartToggle(activeView, hasNetworkPlot) : "";
    if (isCommunityView && activeView === "network") {
        renderCommunityNetworkChart(plotPoints, Array.isArray(networkEdges) ? networkEdges : [], groups, {
            controlsHtml,
            openAnalysisGroupModalByIndex: callbacks.openAnalysisGroupModalByIndex,
        });
        bindCommunityChartToggle(groups, plotPoints, networkEdges);
        return;
    }

    const subjectLabel = "group";
    renderGroupDistributionChart(groups, {
        chartTitle: "How responses are spread across groups",
        chartCaption: `Hover to see the number of responses in each ${subjectLabel}. Click a bar to open the matching ${subjectLabel} responses.`,
        yAxisLabel: "Groups",
        openAnalysisGroupModalByIndex: callbacks.openAnalysisGroupModalByIndex,
        controlsHtml,
    });
    if (isCommunityView) {
        bindCommunityChartToggle(groups, plotPoints, networkEdges);
    }
}


export function renderNgramCharts(buckets) {
    if (!Array.isArray(buckets) || !buckets.length) {
        clearAnalysisChart();
        return;
    }
    renderNgramFrequencyCharts(buckets, callbacks);
}


export function clearAnalysisChart() {
    purgePlotlyCharts(elements.analysisChart);
    elements.analysisChart.hidden = true;
    elements.analysisChart.innerHTML = "";
}


function buildCommunityChartToggle(activeView, hasNetworkPlot) {
    const options = [
        { key: "bar", label: "Bar chart", disabled: false },
        { key: "network", label: "Topic map", disabled: !hasNetworkPlot },
    ];
    return `
        <div class="analysis-chart-toggle" role="group" aria-label="Community chart view">
            ${options.map((option) => `
                <button
                    type="button"
                    class="analysis-chart-toggle-button${activeView === option.key ? " analysis-chart-toggle-button-active" : ""}"
                    data-community-chart-view="${option.key}"
                    aria-pressed="${activeView === option.key ? "true" : "false"}"
                    ${option.disabled ? "disabled" : ""}
                >${option.label}</button>
            `).join("")}
        </div>
    `;
}


function bindCommunityChartToggle(groups, plotPoints, networkEdges) {
    elements.analysisChart.querySelectorAll("[data-community-chart-view]").forEach((button) => {
        if (!(button instanceof HTMLButtonElement)) {
            return;
        }
        button.addEventListener("click", () => {
            const nextView = button.dataset.communityChartView === "network" ? "network" : "bar";
            if (nextView === state.communityChartView) {
                return;
            }
            state.communityChartView = nextView;
            renderAnalysisChart(groups, plotPoints, networkEdges);
        });
    });
}


export { resizeAnalysisPlots };
