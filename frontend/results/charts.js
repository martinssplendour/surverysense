import { RESULT_STORAGE_KEY, elements, state } from "./shared.js";
import {
    buildExampleRowLabel,
    buildPercentLabel,
    displayAnalysisMode,
    displayColumnLabel,
    escapeHtml,
    normalizeValue,
    parseDownloadFilename,
    slugify,
    stripFilenameExtension,
    wrapPlotLabel,
    wrapPlotLabelTwoLines,
} from "./utils.js";

const callbacks = {
    clearAnalysisMessage: () => {},
    handleMissingResultState: () => {},
    openAnalysisGroupModalByIndex: () => {},
    openAnalysisNgramModal: () => {},
    parseJson: async () => ({}),
    renderAnalysisExportControls: () => {},
    renderAnalysisMessage: () => {},
};

const REPORT_EXPORT_MAX_BARS = 12;

export function configureResultsCharts(nextCallbacks) {
    Object.assign(callbacks, nextCallbacks);
}

export function renderAnalysisChart(groups, scatterPoints = []) {
    if (!groups.length) {
        clearAnalysisChart();
        return;
    }

    const modelKey = state.analysisResult?.model_key || state.selectedAnalysisModel;
    if (modelKey === "kmeans" && Array.isArray(scatterPoints) && scatterPoints.length) {
        renderKmeansScatterChart(scatterPoints);
        return;
    }
    const isThemeView = modelKey === "bertopic";
    const subjectLabel = isThemeView ? "theme" : "group";
    const yAxisLabel = isThemeView ? "Theme name" : "Group name";
    const chartTitle = isThemeView
        ? "How responses are spread across themes"
        : "How responses are spread across groups";
    const chartCaption = `Hover to see the number of responses in each ${subjectLabel}. Click a bar to open the matching ${subjectLabel} responses.`;

    elements.analysisChart.hidden = false;
    elements.analysisChart.innerHTML = `
        <div class="analysis-chart-copy">
            <h4 class="analysis-chart-title">${escapeHtml(chartTitle)}</h4>
            <p class="analysis-chart-caption">${escapeHtml(chartCaption)}</p>
        </div>
        <div class="analysis-plot-shell">
            <div class="analysis-plot-surface" id="analysis-group-plot"></div>
        </div>
    `;

    const plotContainer = document.getElementById("analysis-group-plot");
    const rendered = renderInteractiveGroupChart(plotContainer, groups, {
        chartTitle,
        yAxisLabel,
    });
    if (!rendered && plotContainer instanceof HTMLElement) {
        plotContainer.outerHTML = renderFallbackGroupChart(groups);
    }
    queueAnalysisPlotResize();
}

export function renderNgramCharts(buckets) {
    if (!Array.isArray(buckets) || !buckets.length) {
        clearAnalysisChart();
        return;
    }

    elements.analysisChart.hidden = false;
    elements.analysisChart.innerHTML = `
        <div class="analysis-chart-copy">
            <h4 class="analysis-chart-title">Most common words and phrases in the selected responses</h4>
            <p class="analysis-chart-caption">Hover to see how often each word or phrase appears. Click a bar to open the matching responses.</p>
        </div>
        <div class="analysis-plot-grid">
            ${buckets
                .map((bucket, index) => `
                    <div class="analysis-plot-card">
                        <div class="analysis-plot-surface" id="analysis-ngram-plot-${index}"></div>
                    </div>
                `)
                .join("")}
        </div>
    `;

    const plotly = getPlotly();
    if (!plotly) {
        elements.analysisChart.insertAdjacentHTML(
            "beforeend",
            '<p class="analysis-chart-fallback">Interactive charts are unavailable right now, so matching responses cannot be opened from this view.</p>',
        );
        return;
    }

    buckets.forEach((bucket, index) => {
        const plotContainer = document.getElementById(`analysis-ngram-plot-${index}`);
        renderInteractiveNgramChart(plotContainer, bucket, index);
    });
    queueAnalysisPlotResize();
}

export function clearAnalysisChart() {
    purgePlotlyCharts(elements.analysisChart);
    elements.analysisChart.hidden = true;
    elements.analysisChart.innerHTML = "";
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

function renderInteractiveGroupChart(plotContainer, groups, { chartTitle, yAxisLabel }) {
    const plotly = getPlotly();
    if (!plotly || !(plotContainer instanceof HTMLElement)) {
        return false;
    }

    const sortedGroups = groups
        .map((group, index) => ({ group, index }))
        .sort((left, right) => Number(right.group.count || 0) - Number(left.group.count || 0));
    const subjectLabel = yAxisLabel === "Theme name" ? "theme" : "group";
    const figureHeight = Math.max(180, sortedGroups.length * 30);

    const plotPromise = plotly.newPlot(
        plotContainer,
        [
            {
                type: "bar",
                orientation: "h",
                y: sortedGroups.map(({ group }) => wrapPlotLabelTwoLines(group.label || "Unlabelled group")),
                x: sortedGroups.map(({ group }) => Number(group.count || 0)),
                marker: {
                    color: sortedGroups.map(({ group }) => group.is_noise ? "#b8ac9f" : "#4f7a63"),
                    line: {
                        color: sortedGroups.map(({ group }) => group.is_noise ? "#8d8275" : "#355847"),
                        width: 1,
                    },
                },
                customdata: sortedGroups.map(({ group, index }) => ([
                    index,
                    group.label || "Unlabelled group",
                    buildPercentLabel(group.share),
                    buildExampleRowLabel(group.examples),
                    normalizeValue(group.comment),
                ])),
                hovertemplate: [
                    "<b>%{customdata[1]}</b>",
                    "Number of responses: %{x}",
                    "Share of usable responses: %{customdata[2]}",
                    "Representative rows: %{customdata[3]}",
                    "%{customdata[4]}",
                    "<extra></extra>",
                ].join("<br>"),
            },
        ],
        {
            title: {
                text: chartTitle,
                x: 0,
                xanchor: "left",
            },
            height: figureHeight,
            margin: {
                t: 28,
                r: 12,
                b: 36,
                l: 132,
            },
            paper_bgcolor: "rgba(0, 0, 0, 0)",
            plot_bgcolor: "rgba(255, 250, 242, 0.72)",
            font: {
                family: "\"Segoe UI\", Aptos, sans-serif",
                color: "#3d352d",
                size: 8,
            },
            bargap: 0.28,
            xaxis: {
                title: {
                    text: "Number of responses",
                },
                gridcolor: "rgba(89, 68, 42, 0.1)",
                zeroline: false,
            },
            yaxis: {
                title: {
                    text: yAxisLabel,
                },
                automargin: true,
                autorange: "reversed",
            },
        },
        {
            displaylogo: false,
            responsive: true,
            modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d"],
            toImageButtonOptions: {
                filename: `verbatim-${subjectLabel}-distribution`,
            },
        },
    );

    if (plotPromise && typeof plotPromise.then === "function") {
        plotPromise.then(() => {
            if (typeof plotContainer.on === "function") {
                plotContainer.on("plotly_click", (event) => {
                    const point = event?.points?.[0];
                    const groupIndex = Number(point?.customdata?.[0]);
                    if (Number.isFinite(groupIndex)) {
                        callbacks.openAnalysisGroupModalByIndex(groupIndex);
                    }
                });
            }
        });
    }

    return true;
}

function renderKmeansScatterChart(scatterPoints) {
    elements.analysisChart.hidden = false;
    elements.analysisChart.innerHTML = `
        <div class="analysis-plot-shell analysis-plot-shell-wide">
            <div class="analysis-plot-surface analysis-plot-surface-wide" id="analysis-kmeans-plot"></div>
        </div>
    `;

    const plotContainer = document.getElementById("analysis-kmeans-plot");
    const rendered = renderInteractiveKmeansScatterChart(plotContainer, scatterPoints);
    if (!rendered && plotContainer instanceof HTMLElement) {
        plotContainer.outerHTML = `
            <div class="analysis-chart-fallback">
                <p class="analysis-chart-fallback-note">Interactive charts are unavailable right now, so the grouped response cards below show the result instead.</p>
            </div>
        `;
    }
    queueAnalysisPlotResize();
}

function renderInteractiveKmeansScatterChart(plotContainer, scatterPoints) {
    const plotly = getPlotly();
    if (!plotly || !(plotContainer instanceof HTMLElement)) {
        return false;
    }

    const colorPalette = [
        "#4f7a63",
        "#c7923f",
        "#b7685f",
        "#6a7fb3",
        "#8b6fa5",
        "#5f9ea0",
        "#a86d5d",
        "#7c8c55",
        "#9b7f67",
    ];
    const groupedPoints = new Map();
    scatterPoints.forEach((point) => {
        const groupKey = String(point.group_id || "");
        const bucket = groupedPoints.get(groupKey) || {
            groupId: groupKey,
            groupLabel: point.group_label || "Unlabelled group",
            points: [],
        };
        bucket.points.push(point);
        groupedPoints.set(groupKey, bucket);
    });

    const traces = Array.from(groupedPoints.values()).map((bucket, index) => ({
        type: "scatter",
        mode: "markers",
        name: bucket.groupLabel,
        x: bucket.points.map((point) => Number(point.x || 0)),
        y: bucket.points.map((point) => Number(point.y || 0)),
        marker: {
            size: 16,
            color: colorPalette[index % colorPalette.length],
            line: {
                color: "#ffffff",
                width: 1.4,
            },
            opacity: 0.88,
        },
        customdata: bucket.points.map((point) => ([
            point.row_number || 0,
            point.group_id || "",
            point.group_label || "Unlabelled group",
            point.text || "",
        ])),
        hovertemplate: [
            "<b>%{customdata[2]}</b>",
            "Row: %{customdata[0]}",
            "Response: %{customdata[3]}",
            "<extra></extra>",
        ].join("<br>"),
    }));

    const viewportWidth = Math.max(
        window.innerWidth || 0,
        document.documentElement?.clientWidth || 0,
    );
    const plotWidth = Math.round(Math.min(1275, Math.max(810, viewportWidth * 0.81)));
    const plotHeight = Math.round(Math.min(735, Math.max(540, plotWidth * 0.56)));
    const legendMargin = viewportWidth <= 1180 ? 250 : viewportWidth <= 1440 ? 300 : 340;

    const plotPromise = plotly.newPlot(
        plotContainer,
        traces,
        {
            width: plotWidth,
            height: plotHeight,
            margin: {
                t: 40,
                r: legendMargin,
                b: 96,
                l: 96,
            },
            paper_bgcolor: "rgba(0, 0, 0, 0)",
            plot_bgcolor: "rgba(255, 250, 242, 0.72)",
            font: {
                family: "\"Segoe UI Variable Text\", Inter, \"Segoe UI\", Arial, sans-serif",
                color: "#3d352d",
                size: 19,
            },
            xaxis: {
                title: {
                    text: "Position on response map",
                    font: {
                        size: 20,
                    },
                },
                zeroline: false,
                gridcolor: "rgba(89, 68, 42, 0.08)",
                tickfont: {
                    size: 16,
                },
            },
            yaxis: {
                title: {
                    text: "Position on response map",
                    font: {
                        size: 20,
                    },
                },
                zeroline: false,
                gridcolor: "rgba(89, 68, 42, 0.08)",
                tickfont: {
                    size: 16,
                },
            },
            legend: {
                orientation: "v",
                yanchor: "top",
                y: 1,
                xanchor: "left",
                x: 1.03,
                font: {
                    size: 17,
                },
                itemsizing: "constant",
            },
        },
        {
            displaylogo: false,
            responsive: true,
            modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d"],
            toImageButtonOptions: {
                filename: "verbatim-kmeans-response-map",
            },
        },
    );

    if (plotPromise && typeof plotPromise.then === "function") {
        plotPromise.then(() => {
            if (typeof plotContainer.on === "function") {
                plotContainer.on("plotly_click", (event) => {
                    const point = event?.points?.[0];
                    const groupId = String(point?.customdata?.[1] || "");
                    const groupIndex = Array.isArray(state.analysisResult?.groups)
                        ? state.analysisResult.groups.findIndex((group) => String(group.group_id) === groupId)
                        : -1;
                    if (groupIndex >= 0) {
                        callbacks.openAnalysisGroupModalByIndex(groupIndex);
                    }
                });
            }
        });
    }

    return true;
}

function renderInteractiveNgramChart(plotContainer, bucket, bucketIndex) {
    const plotly = getPlotly();
    if (!plotly || !(plotContainer instanceof HTMLElement)) {
        return false;
    }

    const items = Array.isArray(bucket.items) ? bucket.items.slice(0, 10) : [];
    const label = bucket.label || `${bucket.ngram_size}-grams`;
    const itemTypeLabel = Number(bucket.ngram_size || 0) === 1 ? "Word" : "Phrase";
    const figureHeight = Math.max(160, items.length * 22 + 60);
    const colorsBySize = {
        1: "#4f7a63",
        2: "#c7923f",
        3: "#b7685f",
    };

    const plotPromise = plotly.newPlot(
        plotContainer,
        [
            {
                type: "bar",
                orientation: "h",
                y: items.map((item) => wrapPlotLabel(item.term || "", 16)),
                x: items.map((item) => Number(item.count || 0)),
                marker: {
                    color: colorsBySize[Number(bucket.ngram_size || 0)] || "#7a6b5e",
                },
                customdata: items.map((item, itemIndex) => [
                    item.term || "",
                    label,
                    itemIndex,
                    Number(item.document_count || 0),
                ]),
                hovertemplate: [
                    "<b>%{customdata[0]}</b>",
                    "Number of times it appears: %{x}",
                    "Matching responses: %{customdata[3]}",
                    "Phrase list: %{customdata[1]}",
                    "<extra></extra>",
                ].join("<br>"),
            },
        ],
        {
            title: {
                text: label,
                x: 0,
                xanchor: "left",
            },
            height: figureHeight,
            margin: {
                t: 28,
                r: 12,
                b: 36,
                l: 88,
            },
            paper_bgcolor: "rgba(0, 0, 0, 0)",
            plot_bgcolor: "rgba(255, 250, 242, 0.72)",
            font: {
                family: "\"Segoe UI\", Aptos, sans-serif",
                color: "#3d352d",
                size: 8,
            },
            bargap: 0.26,
            xaxis: {
                title: {
                    text: `Number of times the ${itemTypeLabel.toLowerCase()} appears`,
                },
                gridcolor: "rgba(89, 68, 42, 0.1)",
                zeroline: false,
            },
            yaxis: {
                title: {
                    text: itemTypeLabel,
                },
                automargin: true,
                autorange: "reversed",
            },
        },
        {
            displaylogo: false,
            responsive: true,
            modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d"],
            toImageButtonOptions: {
                filename: `verbatim-${label.toLowerCase().replaceAll(" ", "-")}`,
            },
        },
    );

    if (plotPromise && typeof plotPromise.then === "function") {
        plotPromise.then(() => {
            if (typeof plotContainer.on === "function") {
                plotContainer.on("plotly_click", (event) => {
                    const point = event?.points?.[0];
                    const itemIndex = Number(point?.customdata?.[2]);
                    if (Number.isFinite(itemIndex)) {
                        callbacks.openAnalysisNgramModal(bucketIndex, itemIndex);
                    }
                });
            }
        });
    }

    return true;
}

function renderFallbackGroupChart(groups) {
    const maxCount = Math.max(...groups.map((group) => Number(group.count || 0)), 1);

    return `
        <div class="analysis-chart-fallback">
            <p class="analysis-chart-fallback-note">Interactive charts are unavailable right now, so this plain view is shown instead.</p>
            ${groups
                .map((group) => {
                    const count = Number(group.count || 0);
                    const width = Math.max(6, Math.round((count / maxCount) * 100));
                    const percent = typeof group.share === "number" ? Math.round(group.share * 100) : 0;
                    return `
                        <div class="analysis-bar">
                            <div class="analysis-bar-header">
                                <span class="analysis-bar-label">${escapeHtml(group.label)}</span>
                                <span class="analysis-bar-value">${count} responses${percent ? ` | ${percent}%` : ""}</span>
                            </div>
                            <div class="analysis-bar-track">
                                <div class="analysis-bar-fill${group.is_noise ? " analysis-bar-fill-noise" : ""}" style="width:${width}%"></div>
                            </div>
                        </div>
                    `;
                })
                .join("")}
        </div>
    `;
}

function purgePlotlyCharts(container) {
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

function resizeAnalysisPlots() {
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

export { resizeAnalysisPlots };

function queueAnalysisPlotResize() {
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            resizeAnalysisPlots();
        });
    });
}

function getPlotly() {
    return typeof window !== "undefined" && typeof window.Plotly !== "undefined"
        ? window.Plotly
        : null;
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

    const exportHeight = resolveAnalysisExportHeight({ data: limitAnalysisExportData(clonePlotlyFigureValue(plotSurface.data) || [], definition), definition, fallbackHeight: height });
    const exportContainer = document.createElement("div");
    exportContainer.style.position = "fixed";
    exportContainer.style.left = "-10000px";
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

    const barHeight = kind === "ngram" ? 42 : 46;
    return Math.max(560, Math.min(fallbackHeight, barCount * barHeight + 180));
}

function clonePlotlyFigureValue(value) {
    if (value === null || value === undefined) {
        return value;
    }
    return JSON.parse(JSON.stringify(value));
}
