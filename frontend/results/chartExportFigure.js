import { wrapPlotLabelTwoLines } from "./utils.js";
import { getPlotly } from "./plotlyRuntime.js";


const REPORT_EXPORT_MAX_BARS = 12;


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


function buildAnalysisExportLayoutOverrides(definition, baseLayout) {
    const kind = definition?.kind || "";
    const ngramSize = Number(definition?.ngramSize || 0);
    const baseMargin = baseLayout?.margin || {};
    const baseFont = baseLayout?.font || {};
    const baseXAxis = baseLayout?.xaxis || {};
    const baseYAxis = baseLayout?.yaxis || {};

    const overrides = {
        paper_bgcolor: "#fffaf2",
        title: {
            ...(baseLayout?.title || {}),
            text: "",
        },
    };

    if (kind === "ngram") {
        const exportLeftMargin = ngramSize === 3 ? 190 : 172;
        overrides.margin = {
            ...baseMargin,
            l: Math.max(Number(baseMargin.l || 0), exportLeftMargin),
            r: Math.max(Number(baseMargin.r || 0), 12),
            t: Math.max(Number(baseMargin.t || 0), 44),
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
            tickangle: 0,
            tickfont: {
                ...(baseYAxis.tickfont || {}),
                size: ngramSize === 2 ? 12 : (ngramSize === 3 ? 17 : 24),
            },
        };
    }

    if (kind === "group") {
        overrides.margin = {
            ...baseMargin,
            l: Math.max(Number(baseMargin.l || 0), 184),
            t: Math.max(Number(baseMargin.t || 0), 44),
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
            tickangle: 0,
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
                size: Math.max(Number(baseYAxis?.tickfont?.size || 0), 13.5),
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

    return data.map((trace) => {
        if (!trace || trace.type !== "bar" || trace.orientation !== "h") {
            return trace;
        }

        return {
            ...trace,
            x: Array.isArray(trace.x) ? trace.x.slice(0, REPORT_EXPORT_MAX_BARS) : trace.x,
            y: Array.isArray(trace.y)
                ? trace.y
                    .slice(0, REPORT_EXPORT_MAX_BARS)
                    .map((label) => clampExportPlotLabel(label, kind === "group" ? 20 : 18))
                : trace.y,
            customdata: Array.isArray(trace.customdata) ? trace.customdata.slice(0, REPORT_EXPORT_MAX_BARS) : trace.customdata,
            text: Array.isArray(trace.text) ? trace.text.slice(0, REPORT_EXPORT_MAX_BARS) : trace.text,
            hovertext: Array.isArray(trace.hovertext) ? trace.hovertext.slice(0, REPORT_EXPORT_MAX_BARS) : trace.hovertext,
        };
    });
}


function clampExportPlotLabel(label, maxLineLength = 18) {
    const normalized = `${label || ""}`
        .replaceAll("<br>", " ")
        .replace(/\s+/g, " ")
        .trim();
    return wrapPlotLabelTwoLines(normalized, maxLineLength);
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

    const barHeight = kind === "ngram" ? 48 : 52;
    return Math.max(560, Math.min(fallbackHeight, barCount * barHeight + 180));
}


function clonePlotlyFigureValue(value) {
    if (value === null || value === undefined) {
        return value;
    }
    return JSON.parse(JSON.stringify(value));
}
