// Captures rendered Plotly charts or generates export-only charts for reports.
import { elements, state } from "../../shared.js";
import { captureAnalysisChartImage, getPlotly } from "../exportFigure.js";
import { resolveBarChartExportHeight } from "../exportFigureData.js";
import {
    buildAnalysisChartDefinitions,
    resolveAnalysisExportDimensions,
} from "../exportMetadata.js";
import {
    buildGeneratedGroupBarData,
    buildGeneratedGroupBarLayout,
    buildGeneratedNgramBarData,
    buildGeneratedNgramBarLayout,
    normalizeNgramItems,
} from "./generatedChartModels.js";


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
    const baseDimensions = resolveAnalysisExportDimensions({
        definition: chartDefinition,
        fallbackWidth: 900,
        fallbackHeight: 960,
    });
    const dimensions = {
        ...baseDimensions,
        height: resolveBarChartExportHeight({
            kind: "ngram",
            barCount: bucket.items.length,
            fallbackHeight: baseDimensions.height,
        }),
    };
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
            .filter((group) => !group?.is_noise)
            .sort((left, right) => Number(right.count || 0) - Number(left.count || 0))
            .slice(0, 10)
        : [];
    if (!groups.length) {
        return null;
    }

    const definition = buildAnalysisChartDefinitions(1)[0] || {
        title: "Top themes",
        caption: "",
        kind: "group",
    };
    const baseDimensions = resolveAnalysisExportDimensions({
        definition,
        fallbackWidth: 1200,
        fallbackHeight: 1040,
    });
    const dimensions = {
        ...baseDimensions,
        height: resolveBarChartExportHeight({
            kind: "group",
            barCount: groups.length,
            fallbackHeight: baseDimensions.height,
        }),
    };
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
