import { elements } from "./shared.js";
import {
    buildExampleRowLabel,
    buildPercentLabel,
    escapeHtml,
    normalizeValue,
    wrapPlotLabelTwoLines,
} from "./shared/utils.js";
import { getPlotly, queueAnalysisPlotResize, resizeAnalysisPlots } from "./plotlyRuntime.js";


const GROUP_ROW_HEIGHT = 52;
const GROUP_PLOT_VERTICAL_PADDING = 92;
const MIN_GROUP_PLOT_HEIGHT = 360;
const MIN_GROUP_PLOT_WIDTH = 760;
let groupResizeObserver = null;


export function renderGroupDistributionChart(groups, { chartTitle, chartCaption, yAxisLabel, openAnalysisGroupModalByIndex, controlsHtml = "" }) {
    disconnectGroupResizeObserver();
    elements.analysisChart.hidden = false;
    const plotHeight = getGroupFigureHeight(groups);
    elements.analysisChart.innerHTML = `
        <div class="analysis-chart-copy">
            <h4 class="analysis-chart-title">${escapeHtml(chartTitle)}</h4>
            <p class="analysis-chart-caption">${escapeHtml(chartCaption)}</p>
            ${controlsHtml}
        </div>
        <div class="analysis-plot-shell analysis-group-plot-shell" style="--group-plot-min-height: ${plotHeight}px;">
            <div class="analysis-plot-surface" id="analysis-group-plot"></div>
        </div>
    `;

    const plotContainer = document.getElementById("analysis-group-plot");
    const rendered = renderInteractiveGroupChart(plotContainer, groups, {
        chartTitle,
        yAxisLabel,
        openAnalysisGroupModalByIndex,
    });
    if (!rendered && plotContainer instanceof HTMLElement) {
        plotContainer.outerHTML = renderFallbackGroupChart(groups);
    }
    observeResizableGroupPlot();
    queueAnalysisPlotResize();
}


function renderInteractiveGroupChart(plotContainer, groups, { chartTitle, yAxisLabel, openAnalysisGroupModalByIndex }) {
    const plotly = getPlotly();
    if (!plotly || !(plotContainer instanceof HTMLElement)) {
        return false;
    }

    const sortedGroups = groups
        .map((group, index) => ({ group, index }))
        .sort((left, right) => Number(right.group.count || 0) - Number(left.group.count || 0));
    const subjectLabel = yAxisLabel === "Topics" ? "topics" : "groups";
    const wrappedLabels = sortedGroups.map(({ group }) => wrapPlotLabelTwoLines(group.label || "Unlabelled group", 24));
    const longestLabelLineLength = wrappedLabels.reduce(
        (maximum, label) => Math.max(
            maximum,
            ...`${label}`.split("<br>").map((line) => line.length),
        ),
        0,
    );
    const leftMargin = Math.min(300, Math.max(180, longestLabelLineLength * 7 + 44));
    const maxCount = Math.max(...sortedGroups.map(({ group }) => Number(group.count || 0)), 1);
    const figureHeight = getGroupFigureHeight(sortedGroups.map(({ group }) => group));
    plotContainer.style.minHeight = `${figureHeight}px`;

    const plotPromise = plotly.newPlot(
        plotContainer,
        [
            {
                type: "bar",
                orientation: "h",
                y: wrappedLabels,
                x: sortedGroups.map(({ group }) => Number(group.count || 0)),
                text: sortedGroups.map(({ group }) => String(Number(group.count || 0))),
                textposition: "outside",
                cliponaxis: false,
                marker: {
                    color: sortedGroups.map(({ group }) => group.is_noise ? "#b8ac9f" : "#2477F8"),
                    line: {
                        color: sortedGroups.map(({ group }) => group.is_noise ? "#8d8275" : "#1b5dcc"),
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
            height: figureHeight,
            autosize: true,
            margin: {
                t: 18,
                r: 72,
                b: 54,
                l: leftMargin,
            },
            paper_bgcolor: "rgba(0, 0, 0, 0)",
            plot_bgcolor: "rgba(255, 250, 242, 0.72)",
            font: {
                family: "\"Segoe UI\", Aptos, sans-serif",
                color: "#3d352d",
                size: 12,
            },
            bargap: 0.28,
            xaxis: {
                title: {
                    text: "Responses",
                },
                gridcolor: "rgba(89, 68, 42, 0.1)",
                zeroline: false,
                range: [0, Math.ceil(maxCount * 1.08)],
                fixedrange: true,
            },
            yaxis: {
                automargin: true,
                autorange: "reversed",
                tickangle: 0,
                tickfont: {
                    size: 12,
                },
                fixedrange: true,
            },
        },
        {
            displayModeBar: false,
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
                        openAnalysisGroupModalByIndex(groupIndex);
                    }
                });
            }
        });
    }

    return true;
}


function disconnectGroupResizeObserver() {
    if (groupResizeObserver) {
        groupResizeObserver.disconnect();
        groupResizeObserver = null;
    }
}


function observeResizableGroupPlot() {
    if (typeof ResizeObserver === "undefined") {
        return;
    }

    const plotShell = elements.analysisChart.querySelector(".analysis-group-plot-shell");
    const plotSurface = elements.analysisChart.querySelector("#analysis-group-plot");
    if (!(plotShell instanceof HTMLElement) || !(plotSurface instanceof HTMLElement)) {
        return;
    }

    const plotly = getPlotly();
    if (!plotly) {
        return;
    }

    groupResizeObserver = new ResizeObserver(() => {
        try {
            const width = Math.max(MIN_GROUP_PLOT_WIDTH - 32, Math.floor(plotSurface.clientWidth));
            const height = Math.max(MIN_GROUP_PLOT_HEIGHT, Math.floor(plotSurface.clientHeight));
            if (typeof plotly.relayout === "function") {
                plotly.relayout(plotSurface, { width, height });
            } else {
                plotly.Plots.resize(plotSurface);
            }
        } catch (_error) {
            // Ignore resize noise while Plotly is mounting.
        }
    });
    groupResizeObserver.observe(plotShell);
    resizeAnalysisPlots();
}


function getGroupFigureHeight(groups) {
    const groupCount = Array.isArray(groups) ? groups.length : 0;
    return Math.max(MIN_GROUP_PLOT_HEIGHT, GROUP_PLOT_VERTICAL_PADDING + groupCount * GROUP_ROW_HEIGHT);
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
