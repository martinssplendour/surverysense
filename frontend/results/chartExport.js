// Exports analysis results as PDF, DOCX, or PPTX by capturing Plotly chart images and posting them to the backend.
import { RESULT_STORAGE_KEY, elements, state } from "./shared.js";
import {
    displayAnalysisMode,
    displayColumnLabel,
    parseDownloadFilename,
    slugify,
    stripFilenameExtension,
} from "./utils.js";

const REPORT_EXPORT_MAX_BARS = 12;

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
        // Trigger a browser download by creating a temporary <a> element pointing at an object URL.
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

function buildAnalysisExportTitle() {
    if (!state.analysisResult) {
        return "Verbatim Analysis Report";
    }
    return `${displayColumnLabel(state.analysisResult.text_column_name)} - ${state.analysisResult.model_label} Report`;
}

function buildAnalysisExportFileStem() {
    const sourceName = stripFilenameExtension(state.response?.filename || "verbatim-analysis");
    const methodSlug = slugify(displayAnalysisMode(state.analysisResult?.model_key || state.selectedAnalysisModel));
    return `${slugify(sourceName)}-${methodSlug || "analysis"}-report`;
}

function buildAnalysisExportFilters() {
    return Object.entries(state.activeFilters).map(([columnName, values]) => {
        const definition = state.availableFilters.find((item) => item.column_name === columnName) || null;
        return {
            column_name: columnName,
            display_name: definition?.display_name || definition?.column_name || columnName,
            values: Array.isArray(values) ? values : [],
        };
    });
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
                console.warn("[Verbatim App] Unable to capture chart image for export.", error);
                return null;
            }
        }),
    );

    return images.filter(Boolean);
}

function resolveAnalysisExportDimensions({ definition, fallbackWidth, fallbackHeight }) {
    const kind = definition?.kind || "";
    if (kind === "group" || kind === "ngram") {
        return {
            width: 900,
            height: Math.max(900, fallbackHeight),
        };
    }

    return {
        width: fallbackWidth,
        height: fallbackHeight,
    };
}

function buildAnalysisChartDefinitions(surfaceCount) {
    const result = state.analysisResult;
    if (!result) {
        return [];
    }
    const chartCaption = elements.analysisChart?.querySelector(".analysis-chart-caption")?.textContent?.trim() || "";
    const chartTitle = elements.analysisChart?.querySelector(".analysis-chart-title")?.textContent?.trim() || "";

    if (Array.isArray(result.ngram_buckets) && result.ngram_buckets.length) {
        return result.ngram_buckets.slice(0, surfaceCount).map((bucket) => ({
            title: bucket.label || `${bucket.ngram_size}-grams`,
            caption: chartCaption,
            kind: "ngram",
            ngramSize: Number(bucket.ngram_size || 0),
        }));
    }

    if (result.model_key === "kmeans") {
        return [
            {
                title: "Response map",
                caption: "Spatial view of the clustered responses currently shown on screen.",
                kind: "scatter",
            },
        ];
    }

    return [
        {
            title: chartTitle || `${displayAnalysisMode(result.model_key)} distribution`,
            caption: chartCaption,
            kind: "group",
        },
    ];
}

async function captureAnalysisChartImage(plotly, plotSurface, { width, height, definition }) {
    const baseLayout = clonePlotlyFigureValue(plotSurface.layout) || {};
    const exportOverrides = buildAnalysisExportLayoutOverrides(definition, baseLayout);
    if (!Object.keys(exportOverrides).length) {
        return plotly.toImage(plotSurface, {
            format: "png",
            width,
            height,
        });
    }

    const exportHeight = resolveAnalysisExportHeight({
        data: limitAnalysisExportData(clonePlotlyFigureValue(plotSurface.data) || [], definition),
        definition,
        fallbackHeight: height,
    });
    // Render an off-screen Plotly instance with export-tuned layout so the captured image is high-quality.
    const exportContainer = document.createElement("div");
    exportContainer.style.position = "fixed";
    exportContainer.style.left = "-10000px";  // Position off-screen; invisible but still measurable by Plotly.
    exportContainer.style.top = "0";
    exportContainer.style.pointerEvents = "none";
    exportContainer.style.width = `${width}px`;
    exportContainer.style.height = `${exportHeight}px`;
    document.body.appendChild(exportContainer);

    try {
        const data = limitAnalysisExportData(clonePlotlyFigureValue(plotSurface.data) || [], definition);
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

function buildAnalysisExportLayoutOverrides(definition, baseLayout) {
    const kind = definition?.kind || "";
    const ngramSize = Number(definition?.ngramSize || 0);
    const baseMargin = baseLayout?.margin || {};
    const baseFont = baseLayout?.font || {};
    const baseXAxis = baseLayout?.xaxis || {};
    const baseYAxis = baseLayout?.yaxis || {};

    const overrides = {
        paper_bgcolor: "#fffaf2",
    };

    // Report exports need a denser, print-friendly layout than the live dashboard:
    // wider label margins, larger axis text, and capped label height.
    if (kind === "ngram") {
        const exportLeftMargin = ngramSize === 3 ? 180 : 160;
        overrides.margin = {
            ...baseMargin,
            l: Math.max(Number(baseMargin.l || 0), exportLeftMargin),
            r: Math.max(Number(baseMargin.r || 0), 12),
            t: Math.max(Number(baseMargin.t || 0), 30),
            b: Math.max(Number(baseMargin.b || 0), 40),
        };
        overrides.font = {
            ...baseFont,
            size: Math.max(Number(baseFont.size || 0), 11),
        };
        overrides.xaxis = {
            ...baseXAxis,
            title: {
                ...(baseXAxis && typeof baseXAxis.title === "object" ? baseXAxis.title : {}),
                font: {
                    ...((baseXAxis && typeof baseXAxis.title === "object" && typeof baseXAxis.title.font === "object")
                        ? baseXAxis.title.font
                        : {}),
                    size: 16,
                },
            },
            tickfont: {
                ...(baseXAxis.tickfont || {}),
                size: Math.max(Number(baseXAxis?.tickfont?.size || 0), 15),
            },
        };
        overrides.yaxis = {
            ...baseYAxis,
            title: {
                ...(baseYAxis && typeof baseYAxis.title === "object" ? baseYAxis.title : {}),
                text: "",
            },
            automargin: true,
            tickangle: -18,
            tickfont: {
                ...(baseYAxis.tickfont || {}),
                size: Math.max(Number(baseYAxis?.tickfont?.size || 0), ngramSize === 3 ? 34 : 48),
            },
        };
    }

    if (kind === "group") {
        overrides.margin = {
            ...baseMargin,
            l: Math.max(Number(baseMargin.l || 0), 160),
            b: Math.max(Number(baseMargin.b || 0), 58),
        };
        overrides.xaxis = {
            ...baseXAxis,
            title: {
                ...(baseXAxis && typeof baseXAxis.title === "object" ? baseXAxis.title : {}),
                standoff: 18,
                font: {
                    ...((baseXAxis && typeof baseXAxis.title === "object" && typeof baseXAxis.title.font === "object")
                        ? baseXAxis.title.font
                        : {}),
                    size: 16,
                },
            },
            tickfont: {
                ...(baseXAxis.tickfont || {}),
                size: Math.max(Number(baseXAxis?.tickfont?.size || 0), 15),
            },
        };
        overrides.yaxis = {
            ...baseYAxis,
            automargin: true,
            tickangle: -18,
            title: {
                ...(baseYAxis && typeof baseYAxis.title === "object" ? baseYAxis.title : {}),
                text: "Topic names",
                font: {
                    ...((baseYAxis && typeof baseYAxis.title === "object" && typeof baseYAxis.title.font === "object")
                        ? baseYAxis.title.font
                        : {}),
                    size: 16,
                },
            },
            tickfont: {
                ...(baseYAxis.tickfont || {}),
                size: Math.max(Number(baseYAxis?.tickfont?.size || 0), 15),
            },
        };
    }

    return overrides;
}

function limitAnalysisExportData(data, definition) {
    const kind = definition?.kind || "";
    if (kind !== "group" && kind !== "ngram") {
        return data;
    }

    // Reports only keep the first N horizontal bars; the live chart can stay more
    // interactive, but the exported page/slide needs a readable fixed height.
    return data.map((trace) => {
        if (!trace || trace.type !== "bar" || trace.orientation !== "h") {
            return trace;
        }

        return {
            ...trace,
            x: Array.isArray(trace.x) ? trace.x.slice(0, REPORT_EXPORT_MAX_BARS) : trace.x,
            y: Array.isArray(trace.y)
                ? trace.y.slice(0, REPORT_EXPORT_MAX_BARS).map((label) => clampExportPlotLabel(label))
                : trace.y,
            customdata: Array.isArray(trace.customdata) ? trace.customdata.slice(0, REPORT_EXPORT_MAX_BARS) : trace.customdata,
            text: Array.isArray(trace.text) ? trace.text.slice(0, REPORT_EXPORT_MAX_BARS) : trace.text,
            hovertext: Array.isArray(trace.hovertext) ? trace.hovertext.slice(0, REPORT_EXPORT_MAX_BARS) : trace.hovertext,
        };
    });
}

function clampExportPlotLabel(label) {
    const normalized = `${label || ""}`
        .split("<br>")
        .map((part) => part.trim())
        .filter(Boolean);
    if (!normalized.length) {
        return "Untitled";
    }
    if (normalized.length <= 2) {
        return normalized.join("<br>");
    }

    const secondLine = normalized.slice(1).join(" ");
    const truncatedSecondLine = secondLine.length > 18
        ? `${secondLine.slice(0, 15).trimEnd()}...`
        : secondLine;
    return `${normalized[0]}<br>${truncatedSecondLine}`;
}

function resolveAnalysisExportHeight({ data, definition, fallbackHeight }) {
    const kind = definition?.kind || "";
    if (kind !== "group" && kind !== "ngram") {
        return fallbackHeight;
    }

    const firstBarTrace = Array.isArray(data)
        ? data.find((trace) => trace && trace.type === "bar" && trace.orientation === "h")
        : null;
    const barCount = Array.isArray(firstBarTrace?.y) ? firstBarTrace.y.length : 0;
    if (!barCount) {
        return fallbackHeight;
    }

    // Height follows the trimmed bar count so export images do not keep the huge
    // whitespace from the on-screen canvas after bars are removed.
    const barHeight = kind === "ngram" ? 42 : 46;
    return Math.max(560, Math.min(fallbackHeight, barCount * barHeight + 180));
}

function clonePlotlyFigureValue(value) {
    if (value === null || value === undefined) {
        return value;
    }
    return JSON.parse(JSON.stringify(value));
}

function getPlotly() {
    return typeof window !== "undefined" && typeof window.Plotly !== "undefined"
        ? window.Plotly
        : null;
}
