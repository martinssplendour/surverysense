import { elements } from "../shared.js";


export function purgePlotlyCharts(container) {
    const plotly = getPlotly();
    if (!plotly || !(container instanceof HTMLElement)) {
        return;
    }

    container.querySelectorAll(".analysis-plot-surface").forEach((plotSurface) => {
        try {
            plotly.purge(plotSurface);
        } catch (_error) {
            // Ignore Plotly cleanup issues when the chart has already been discarded.
        }
    });
}


export function resizeAnalysisPlots() {
    const plotly = getPlotly();
    if (!plotly || elements.analysisChart.hidden) {
        return;
    }

    elements.analysisChart.querySelectorAll(".analysis-plot-surface").forEach((plotSurface) => {
        try {
            plotly.Plots.resize(plotSurface);
        } catch (_error) {
            // Ignore resize failures for charts that are being re-rendered.
        }
    });
}


export function queueAnalysisPlotResize() {
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            resizeAnalysisPlots();
        });
    });
}


export function getPlotly() {
    return typeof window !== "undefined" && typeof window.Plotly !== "undefined"
        ? window.Plotly
        : null;
}
