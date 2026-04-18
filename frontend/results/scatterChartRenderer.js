import { elements, state } from "./shared.js";
import { getPlotly, queueAnalysisPlotResize } from "./plotlyRuntime.js";


export function renderKmeansScatterChart(scatterPoints, { openAnalysisGroupModalByIndex }) {
    elements.analysisChart.hidden = false;
    elements.analysisChart.innerHTML = `
        <div class="analysis-plot-shell analysis-plot-shell-wide">
            <div class="analysis-plot-surface analysis-plot-surface-wide" id="analysis-kmeans-plot"></div>
        </div>
    `;

    const plotContainer = document.getElementById("analysis-kmeans-plot");
    const rendered = renderInteractiveKmeansScatterChart(plotContainer, scatterPoints, { openAnalysisGroupModalByIndex });
    if (!rendered && plotContainer instanceof HTMLElement) {
        plotContainer.outerHTML = `
            <div class="analysis-chart-fallback">
                <p class="analysis-chart-fallback-note">Interactive charts are unavailable right now, so the grouped response cards below show the result instead.</p>
            </div>
        `;
    }
    queueAnalysisPlotResize();
}


function renderInteractiveKmeansScatterChart(plotContainer, scatterPoints, { openAnalysisGroupModalByIndex }) {
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
                        openAnalysisGroupModalByIndex(groupIndex);
                    }
                });
            }
        });
    }

    return true;
}
