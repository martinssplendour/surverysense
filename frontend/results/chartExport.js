// Exports analysis results as PDF, DOCX, or PPTX by capturing Plotly chart images and posting them to the backend.
import { RESULT_STORAGE_KEY, elements, state } from "./shared.js";
import { parseDownloadFilename } from "./utils.js";
import { captureAnalysisChartImage, getPlotly } from "./chartExportFigure.js";
import {
    buildAnalysisChartDefinitions,
    buildAnalysisExportFileStem,
    buildAnalysisExportFilters,
    buildAnalysisExportTitle,
    resolveAnalysisExportDimensions,
} from "./chartExportMetadata.js";


const callbacks = {
    clearAnalysisMessage: () => {},
    handleMissingResultState: () => {},
    parseJson: async () => ({}),
    renderAnalysisExportControls: () => {},
    renderAnalysisMessage: () => {},
};


export function configureChartExport(nextCallbacks) {
    Object.assign(callbacks, nextCallbacks);
}


export function normalizeAnalysisExportFormat(value) {
    return value === "docx" || value === "pptx" || value === "pdf"
        ? value
        : "pdf";
}


export function displayAnalysisExportFormat(value) {
    switch (normalizeAnalysisExportFormat(value)) {
    case "docx":
        return "Doc";
    case "pptx":
        return "Slides";
    default:
        return "PDF";
    }
}


export async function downloadAnalysisReport() {
    if (!state.resultId || !state.analysisResult?.ok || state.analysisExportRunning) {
        return;
    }

    state.analysisExportFormat = normalizeAnalysisExportFormat(state.analysisExportFormat);
    state.analysisExportMenuOpen = false;
    state.analysisExportRunning = true;
    callbacks.renderAnalysisExportControls();

    try {
        const charts = await captureRenderedAnalysisCharts();
        const response = await fetch(`/analysis-export/${encodeURIComponent(state.resultId)}`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                format: state.analysisExportFormat || "pdf",
                report_title: buildAnalysisExportTitle(),
                source_filename: state.response?.filename || "",
                subtitle: elements.analysisResultsSubtitle?.textContent?.trim() || "",
                active_filters: buildAnalysisExportFilters(),
                charts,
                analysis_result: state.analysisResult,
            }),
        });
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
            throw new Error(payload.detail || "Unable to export the report.");
        }

        const blob = await response.blob();
        const objectUrl = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = objectUrl;
        anchor.download = parseDownloadFilename(response.headers.get("Content-Disposition"))
            || `${buildAnalysisExportFileStem()}.${state.analysisExportFormat || "pdf"}`;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(objectUrl);
        callbacks.clearAnalysisMessage();
    } catch (error) {
        const message = error instanceof Error ? error.message : "Unable to export the report.";
        callbacks.renderAnalysisMessage("error", message);
    } finally {
        state.analysisExportRunning = false;
        callbacks.renderAnalysisExportControls();
    }
}


async function captureRenderedAnalysisCharts() {
    const plotly = getPlotly();
    if (!plotly || typeof plotly.toImage !== "function" || !(elements.analysisChart instanceof HTMLElement)) {
        return [];
    }

    const plotSurfaces = Array.from(elements.analysisChart.querySelectorAll(".analysis-plot-surface"));
    if (!plotSurfaces.length) {
        return [];
    }

    const chartDefinitions = buildAnalysisChartDefinitions(plotSurfaces.length);
    const images = await Promise.all(
        plotSurfaces.map(async (plotSurface, index) => {
            if (!(plotSurface instanceof HTMLElement)) {
                return null;
            }
            const rect = plotSurface.getBoundingClientRect();
            try {
                const definition = chartDefinitions[index] || chartDefinitions[0] || {
                    title: `Chart ${index + 1}`,
                    caption: "",
                };
                const { width, height } = resolveAnalysisExportDimensions({
                    definition,
                    fallbackWidth: Math.max(1200, Math.round(rect.width * 2) || 1200),
                    fallbackHeight: Math.max(720, Math.round(rect.height * 2) || 720),
                });
                const imageDataUrl = await captureAnalysisChartImage(plotly, plotSurface, {
                    width,
                    height,
                    definition,
                });
                return {
                    title: definition.title,
                    caption: definition.caption,
                    image_data_url: imageDataUrl,
                };
            } catch (error) {
                console.warn(
                    `[Verbatim App] Failed to capture export image for chart ${index + 1}; the report will skip that chart.`,
                    error,
                );
                return null;
            }
        }),
    );

    return images.filter(Boolean);
}
