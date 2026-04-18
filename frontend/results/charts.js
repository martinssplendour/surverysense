// Builds and manages Plotly charts for topic/group distribution, K-means scatter, and n-gram frequency.
import { elements, state } from "./shared.js";
import { configureChartExport } from "./chartExport.js";
import { renderGroupDistributionChart } from "./groupChartRenderer.js";
import { renderNgramFrequencyCharts } from "./ngramChartRenderer.js";
import { purgePlotlyCharts, resizeAnalysisPlots } from "./plotlyRuntime.js";
import { renderKmeansScatterChart } from "./scatterChartRenderer.js";


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


export function renderAnalysisChart(groups, scatterPoints = []) {
    if (!groups.length) {
        clearAnalysisChart();
        return;
    }

    const modelKey = state.analysisResult?.model_key || state.selectedAnalysisModel;
    if (modelKey === "kmeans" && Array.isArray(scatterPoints) && scatterPoints.length) {
        renderKmeansScatterChart(scatterPoints, callbacks);
        return;
    }

    const isThemeView = modelKey === "bertopic";
    const subjectLabel = isThemeView ? "topic" : "group";
    renderGroupDistributionChart(groups, {
        chartTitle: isThemeView
            ? "How responses are spread across topics"
            : "How responses are spread across groups",
        chartCaption: `Hover to see the number of responses in each ${subjectLabel}. Click a bar to open the matching ${subjectLabel} responses.`,
        yAxisLabel: isThemeView ? "Topic name" : "Group name",
        openAnalysisGroupModalByIndex: callbacks.openAnalysisGroupModalByIndex,
    });
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


export { resizeAnalysisPlots };
