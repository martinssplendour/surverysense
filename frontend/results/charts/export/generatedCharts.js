// Captures rendered Plotly charts or generates export-only charts for reports.
import { elements, state } from "../../shared.js";
import { captureAnalysisChartImage, getPlotly } from "../exportFigure.js";
import {
    buildAnalysisChartDefinitions,
    resolveAnalysisExportDimensions,
} from "../exportMetadata.js";


export async function captureRenderedAnalysisCharts() {
    const plotly = getPlotly();
    if (!plotly || typeof plotly.toImage !== "function" || !(elements.analysisChart instanceof HTMLElement)) {
        return [];
    }

    if (Array.isArray(state.analysisResult?.groups) && state.analysisResult.groups.length) {
        const generatedGroupChart = await captureGeneratedGroupBarChart(plotly);
        return generatedGroupChart ? [generatedGroupChart] : [];
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


async function captureGeneratedGroupBarChart(plotly) {
    const groups = Array.isArray(state.analysisResult?.groups)
        ? [...state.analysisResult.groups]
            .sort((left, right) => Number(right.count || 0) - Number(left.count || 0))
            .slice(0, 12)
        : [];
    if (!groups.length) {
        return null;
    }

    const definition = buildAnalysisChartDefinitions(1)[0] || {
        title: "Top themes",
        caption: "",
        kind: "group",
    };
    const dimensions = resolveAnalysisExportDimensions({
        definition,
        fallbackWidth: 1200,
        fallbackHeight: Math.max(1170, groups.length * 78 + 230),
    });
    const plotSurface = document.createElement("div");
    plotSurface.style.position = "fixed";
    plotSurface.style.left = "-10000px";
    plotSurface.style.top = "0";
    plotSurface.style.pointerEvents = "none";
    plotSurface.style.width = `${dimensions.width}px`;
    plotSurface.style.height = `${dimensions.height}px`;
    document.body.appendChild(plotSurface);

    try {
        await plotly.newPlot(
            plotSurface,
            buildGeneratedGroupBarData(groups),
            buildGeneratedGroupBarLayout(groups, dimensions),
            {
                displaylogo: false,
                responsive: false,
                staticPlot: true,
            },
        );
        return {
            title: definition.title || "Top themes",
            caption: definition.caption || "",
            image_data_url: await captureAnalysisChartImage(plotly, plotSurface, {
                width: dimensions.width,
                height: dimensions.height,
                definition,
            }),
        };
    } catch (error) {
        console.warn("[Verbatim App] Failed to generate the export bar chart; the report will skip that chart.", error);
        return null;
    } finally {
        if (typeof plotly.purge === "function") {
            plotly.purge(plotSurface);
        }
        plotSurface.remove();
    }
}


function buildGeneratedGroupBarData(groups) {
    return [
        {
            type: "bar",
            orientation: "h",
            y: groups.map((group) => group.label || "Unlabelled theme"),
            x: groups.map((group) => Number(group.count || 0)),
            text: groups.map((group) => String(Number(group.count || 0))),
            textposition: "outside",
            textfont: {
                size: 16,
                color: "#172033",
            },
            cliponaxis: false,
            marker: {
                color: groups.map((group) => group.is_noise ? "#9aa4b2" : "#2477F8"),
                line: {
                    color: groups.map((group) => group.is_noise ? "#818b98" : "#1b5dcc"),
                    width: 1,
                },
            },
            hovertemplate: [
                "<b>%{y}</b>",
                "Responses: %{x}",
                "<extra></extra>",
            ].join("<br>"),
        },
    ];
}


function buildGeneratedGroupBarLayout(groups, { width, height }) {
    const maxCount = Math.max(...groups.map((group) => Number(group.count || 0)), 1);
    return {
        width,
        height,
        autosize: false,
        margin: {
            t: 30,
            r: 46,
            b: 86,
            l: 292,
        },
        paper_bgcolor: "rgba(0, 0, 0, 0)",
        plot_bgcolor: "#ffffff",
        font: {
            family: "\"Segoe UI\", Aptos, sans-serif",
            color: "#172033",
            size: 16,
        },
        uniformtext: {
            minsize: 16,
            mode: "show",
        },
        bargap: 0.28,
        xaxis: {
            title: {
                text: "Responses",
            },
            gridcolor: "rgba(89, 104, 128, 0.12)",
            zeroline: false,
            range: [0, Math.ceil(maxCount * 1.04)],
            fixedrange: true,
        },
        yaxis: {
            automargin: true,
            autorange: "reversed",
            tickangle: 0,
            tickfont: {
                size: 18,
            },
            fixedrange: true,
        },
    };
}
