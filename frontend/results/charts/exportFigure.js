import { getPlotly } from "./plotlyRuntime.js";
import {
    clonePlotlyFigureValue,
    limitAnalysisExportData,
    resolveAnalysisExportHeight,
} from "./exportFigureData.js";
import { buildAnalysisExportLayoutOverrides } from "./exportFigureLayout.js";


export { getPlotly };


export async function captureAnalysisChartImage(plotly, plotSurface, { width, height, definition }) {
    const baseLayout = clonePlotlyFigureValue(plotSurface.layout) || {};
    const exportOverrides = buildAnalysisExportLayoutOverrides(definition, baseLayout);
    if (!Object.keys(exportOverrides).length) {
        return plotly.toImage(plotSurface, {
            format: "png",
            width,
            height,
        });
    }

    const data = limitAnalysisExportData(clonePlotlyFigureValue(plotSurface.data) || [], definition);
    const exportHeight = resolveAnalysisExportHeight({
        data,
        definition,
        fallbackHeight: height,
    });
    const exportContainer = document.createElement("div");
    exportContainer.style.position = "fixed";
    exportContainer.style.left = "-10000px";
    exportContainer.style.top = "0";
    exportContainer.style.pointerEvents = "none";
    exportContainer.style.width = `${width}px`;
    exportContainer.style.height = `${exportHeight}px`;
    document.body.appendChild(exportContainer);

    try {
        const layout = {
            ...baseLayout,
            ...exportOverrides,
            width,
            height: exportHeight,
        };
        const config = {
            displaylogo: false,
            responsive: false,
            modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d"],
            staticPlot: true,
        };
        await plotly.newPlot(exportContainer, data, layout, config);
        return await plotly.toImage(exportContainer, {
            format: "png",
            width,
            height: exportHeight,
        });
    } finally {
        if (typeof plotly.purge === "function") {
            plotly.purge(exportContainer);
        }
        exportContainer.remove();
    }
}
