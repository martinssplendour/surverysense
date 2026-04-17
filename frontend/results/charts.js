// Builds and manages Plotly charts for topic/group distribution (bar), K-means scatter, and n-gram frequency.
import { elements, state } from "./shared.js";
import {
    buildExampleRowLabel,
    buildPercentLabel,
    escapeHtml,
    normalizeValue,
    wrapPlotLabel,
    wrapPlotLabelTwoLines,
} from "./utils.js";
import { configureChartExport } from "./chartExport.js";

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
        renderKmeansScatterChart(scatterPoints);
        return;
    }
    const isThemeView = modelKey === "bertopic";
    const subjectLabel = isThemeView ? "topic" : "group";
    const yAxisLabel = isThemeView ? "Topic name" : "Group name";
    const chartTitle = isThemeView
        ? "How responses are spread across topics"
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

function renderInteractiveGroupChart(plotContainer, groups, { chartTitle, yAxisLabel }) {
    const plotly = getPlotly();
    if (!plotly || !(plotContainer instanceof HTMLElement)) {
        return false;
    }

    const sortedGroups = groups
        .map((group, index) => ({ group, index }))
        .sort((left, right) => Number(right.group.count || 0) - Number(left.group.count || 0));
    const subjectLabel = yAxisLabel === "Topic name" ? "topic" : "group";
    const wrappedLabels = sortedGroups.map(({ group }) => wrapPlotLabelTwoLines(group.label || "Unlabelled group", 20));
    const longestLabelLineLength = wrappedLabels.reduce(
        (maximum, label) => Math.max(
            maximum,
            ...`${label}`.split("<br>").map((line) => line.length),
        ),
        0,
    );
    const leftMargin = Math.min(216, Math.max(156, longestLabelLineLength * 6 + 36));
    const figureHeight = Math.max(216, sortedGroups.length * 36);

    // Plotly config: hide branding, allow responsive resize, remove unused selection tools.
    const plotPromise = plotly.newPlot(
        plotContainer,
        [
            {
                type: "bar",
                orientation: "h",
                y: wrappedLabels,
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
                    "Responses: %{x}",
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
                l: leftMargin,
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
                tickangle: 0,
                tickfont: {
                    size: 7.2,
                },
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

    // customdata[0] carries the original (pre-sort) group index, used to look up the group in state.
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
            size: 8,
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
    const plotWidth = Math.round(Math.min(1245, Math.max(790, viewportWidth * 0.79)));
    const plotHeight = Math.round(Math.min(405, Math.max(297, plotWidth * 0.62)));
    const legendMargin = viewportWidth <= 1180 ? 150 : viewportWidth <= 1440 ? 190 : 220;

    const plotPromise = plotly.newPlot(
        plotContainer,
        traces,
        {
            width: plotWidth,
            height: plotHeight,
            margin: {
                t: 18,
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
                // These are projected embedding coordinates, not original CSV values.
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
                // Same projection space as x; the scatter is for visual separation only.
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
                    size: 9,
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

/**
 * Tells Plotly to recalculate layout for every visible plot surface.
 * Called on window resize so charts fill their containers after the viewport changes.
 */
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

// Two rAF ticks give the browser time to paint the new DOM before Plotly measures container dimensions.
function queueAnalysisPlotResize() {
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            resizeAnalysisPlots();
        });
    });
}

// Plotly is loaded as a global script tag rather than an npm module, so check window at call time.
function getPlotly() {
    return typeof window !== "undefined" && typeof window.Plotly !== "undefined"
        ? window.Plotly
        : null;
}
