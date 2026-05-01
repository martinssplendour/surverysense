// Captures rendered Plotly charts or generates export-only charts for reports.
import { elements, state } from "../../shared.js";
import { captureAnalysisChartImage, getPlotly } from "../exportFigure.js";
import {
    buildAnalysisChartDefinitions,
    resolveAnalysisExportDimensions,
} from "../exportMetadata.js";


const MAX_GENERATED_NGRAM_BARS = 12;


export async function captureRenderedAnalysisCharts() {
    const plotly = getPlotly();
    if (!plotly || typeof plotly.toImage !== "function" || !(elements.analysisChart instanceof HTMLElement)) {
        return [];
    }

    if (Array.isArray(state.analysisResult?.groups) && state.analysisResult.groups.length) {
        const generatedGroupChart = await captureGeneratedGroupBarChart(plotly);
        return generatedGroupChart ? [generatedGroupChart] : [];
    }

    if (Array.isArray(state.analysisResult?.ngram_buckets) && state.analysisResult.ngram_buckets.length) {
        return captureGeneratedNgramCharts(plotly);
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


async function captureGeneratedNgramCharts(plotly) {
    const definitions = buildAnalysisChartDefinitions(state.analysisResult.ngram_buckets.length);
    const buckets = state.analysisResult.ngram_buckets
        .map((bucket, index) => ({
            ...bucket,
            definition: definitions[index],
            items: normalizeNgramItems(bucket.items),
        }))
        .filter((bucket) => bucket.items.length);
    if (!buckets.length) {
        return [];
    }

    const images = [];
    for (const [index, bucket] of buckets.entries()) {
        const image = await captureGeneratedNgramChart(plotly, bucket, bucket.definition, index);
        if (image) {
            images.push(image);
        }
    }
    return images;
}


async function captureGeneratedNgramChart(plotly, bucket, definition, index) {
    const chartDefinition = definition || {
        title: bucket.label || `${bucket.ngram_size}-grams`,
        caption: "",
        kind: "ngram",
        ngramSize: Number(bucket.ngram_size || 0),
    };
    const dimensions = resolveAnalysisExportDimensions({
        definition: chartDefinition,
        fallbackWidth: 900,
        fallbackHeight: Math.max(760, bucket.items.length * 64 + 220),
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
            buildGeneratedNgramBarData(bucket.items),
            buildGeneratedNgramBarLayout(bucket.items, dimensions),
            {
                displaylogo: false,
                responsive: false,
                staticPlot: true,
            },
        );
        return {
            title: chartDefinition.title || bucket.label || `N-gram chart ${index + 1}`,
            caption: chartDefinition.caption || "",
            image_data_url: await captureAnalysisChartImage(plotly, plotSurface, {
                width: dimensions.width,
                height: dimensions.height,
                definition: chartDefinition,
            }),
        };
    } catch (error) {
        console.warn(
            `[Verbatim App] Failed to generate n-gram export chart ${index + 1}; the report will skip that chart.`,
            error,
        );
        return null;
    } finally {
        if (typeof plotly.purge === "function") {
            plotly.purge(plotSurface);
        }
        plotSurface.remove();
    }
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


function normalizeNgramItems(items) {
    return Array.isArray(items)
        ? [...items]
            .map((item) => ({
                ...item,
                count: Number(item.count || 0),
                document_count: Number(item.document_count || 0),
                term: `${item.term || ""}`.trim(),
            }))
            .filter((item) => item.term && item.count > 0)
            .sort((left, right) => right.count - left.count)
            .slice(0, MAX_GENERATED_NGRAM_BARS)
        : [];
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


function buildGeneratedNgramBarData(items) {
    return [
        {
            type: "bar",
            orientation: "h",
            y: items.map((item) => item.term),
            x: items.map((item) => item.count),
            text: items.map((item) => String(item.count)),
            textposition: "outside",
            textfont: {
                size: 15,
                color: "#172033",
            },
            cliponaxis: false,
            customdata: items.map((item) => [item.document_count]),
            marker: {
                color: "#2477F8",
                line: {
                    color: "#1b5dcc",
                    width: 1,
                },
            },
            hovertemplate: [
                "<b>%{y}</b>",
                "Occurrences: %{x}",
                "Matching responses: %{customdata[0]}",
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


function buildGeneratedNgramBarLayout(items, { width, height }) {
    const maxCount = Math.max(...items.map((item) => Number(item.count || 0)), 1);
    return {
        width,
        height,
        autosize: false,
        margin: {
            t: 30,
            r: 42,
            b: 74,
            l: 190,
        },
        paper_bgcolor: "rgba(0, 0, 0, 0)",
        plot_bgcolor: "#ffffff",
        font: {
            family: "\"Segoe UI\", Aptos, sans-serif",
            color: "#172033",
            size: 14,
        },
        uniformtext: {
            minsize: 14,
            mode: "show",
        },
        bargap: 0.24,
        xaxis: {
            title: {
                text: "Occurrences",
            },
            gridcolor: "rgba(89, 104, 128, 0.12)",
            zeroline: false,
            range: [0, Math.ceil(maxCount * 1.08)],
            fixedrange: true,
        },
        yaxis: {
            automargin: true,
            autorange: "reversed",
            tickangle: 0,
            tickfont: {
                size: 16,
            },
            fixedrange: true,
        },
    };
}
