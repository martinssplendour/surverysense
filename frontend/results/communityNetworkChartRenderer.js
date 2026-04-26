import { elements } from "./shared.js";
import {
    buildExampleRowLabel,
    buildPercentLabel,
    escapeHtml,
    normalizeValue,
} from "./shared/utils.js";
import { getPlotly, queueAnalysisPlotResize } from "./plotlyRuntime.js";


const COMMUNITY_COLORS = [
    "#2477F8",
    "#9a5b2e",
    "#3d6790",
    "#7a6042",
    "#6b8ff8",
    "#8b5a6b",
    "#4b6fe8",
    "#a07a35",
];


export function renderCommunityNetworkChart(points, edges, groups, { controlsHtml, openAnalysisGroupModalByIndex }) {
    elements.analysisChart.hidden = false;
    elements.analysisChart.innerHTML = `
        <div class="analysis-chart-copy">
            <h4 class="analysis-chart-title">Community detection network</h4>
            <p class="analysis-chart-caption">Each dot is a response. Lines connect responses that were similar enough to influence community detection. Click a dot to open that community.</p>
            ${controlsHtml}
        </div>
        <div class="analysis-plot-shell">
            <div class="analysis-plot-surface analysis-plot-surface-wide" id="analysis-community-network-plot"></div>
        </div>
    `;

    const plotContainer = document.getElementById("analysis-community-network-plot");
    const rendered = renderInteractiveNetworkChart(plotContainer, points, edges, groups, {
        openAnalysisGroupModalByIndex,
    });
    if (!rendered && plotContainer instanceof HTMLElement) {
        plotContainer.outerHTML = renderFallbackNetworkChart(points);
    }
    queueAnalysisPlotResize();
}


function renderInteractiveNetworkChart(plotContainer, points, edges, groups, { openAnalysisGroupModalByIndex }) {
    const plotly = getPlotly();
    if (!plotly || !(plotContainer instanceof HTMLElement)) {
        return false;
    }

    const pointByIndex = new Map(points.map((point) => [Number(point.point_index), point]));
    const pointByRowNumber = new Map(points.map((point) => [Number(point.row_number), point]));
    const edgeX = [];
    const edgeY = [];
    for (const edge of edges) {
        const source = pointByIndex.get(Number(edge.source_point_index)) || pointByRowNumber.get(Number(edge.source_row_number));
        const target = pointByIndex.get(Number(edge.target_point_index)) || pointByRowNumber.get(Number(edge.target_row_number));
        if (!source || !target) {
            continue;
        }
        edgeX.push(Number(source.x), Number(target.x), null);
        edgeY.push(Number(source.y), Number(target.y), null);
    }

    const groupIndexById = new Map(groups.map((group, index) => [String(group.group_id), index]));
    const groupedPoints = new Map();
    for (const point of points) {
        const groupId = String(point.group_id ?? "");
        if (!groupedPoints.has(groupId)) {
            groupedPoints.set(groupId, []);
        }
        groupedPoints.get(groupId).push(point);
    }

    const traces = [];
    if (edgeX.length) {
        traces.push({
            type: "scatter",
            mode: "lines",
            x: edgeX,
            y: edgeY,
            line: {
                color: "rgba(36, 119, 248, 0.16)",
                width: 1,
            },
            hoverinfo: "skip",
            showlegend: false,
        });
    }

    Array.from(groupedPoints.entries()).forEach(([groupId, groupPoints], index) => {
        const groupIndex = groupIndexById.get(groupId);
        const group = Number.isInteger(groupIndex) ? groups[groupIndex] : null;
        const label = group?.label || groupPoints[0]?.group_label || `Community ${groupId}`;
        traces.push({
            type: "scatter",
            mode: "markers",
            name: label,
            x: groupPoints.map((point) => Number(point.x)),
            y: groupPoints.map((point) => Number(point.y)),
            marker: {
                color: COMMUNITY_COLORS[index % COMMUNITY_COLORS.length],
                size: groupPoints.map((point) => point.text && point.text.length > 140 ? 13 : 11),
                line: {
                    color: "#ffffff",
                    width: 1.5,
                },
                opacity: 0.88,
            },
            customdata: groupPoints.map((point) => {
                const sourceText = normalizeValue(point.source_text || point.text);
                const fragmentText = normalizeValue(point.text);
                const fragmentLabel = sourceText && fragmentText && sourceText !== fragmentText
                    ? `Fragment: ${fragmentText}`
                    : "";
                return [
                groupIndex,
                point.row_number,
                label,
                sourceText,
                group ? buildPercentLabel(group.share) : "",
                group ? buildExampleRowLabel(group.examples) : "",
                group ? normalizeValue(group.comment) : "",
                fragmentLabel,
                ];
            }),
            hovertemplate: [
                "<b>%{customdata[2]}</b>",
                "Row: %{customdata[1]}",
                "%{customdata[3]}",
                "%{customdata[7]}",
                "<extra></extra>",
            ].join("<br>"),
        });
    });

    const plotPromise = plotly.newPlot(
        plotContainer,
        traces,
        {
            height: Math.max(420, Math.min(720, 280 + points.length * 4)),
            margin: {
                t: 18,
                r: 18,
                b: 18,
                l: 18,
            },
            paper_bgcolor: "rgba(0, 0, 0, 0)",
            plot_bgcolor: "rgba(255, 250, 242, 0.72)",
            font: {
                family: "\"Segoe UI\", Aptos, sans-serif",
                color: "#3d352d",
                size: 12,
            },
            xaxis: {
                visible: false,
                zeroline: false,
            },
            yaxis: {
                visible: false,
                zeroline: false,
                scaleanchor: "x",
                scaleratio: 1,
            },
            legend: {
                orientation: "h",
                x: 0,
                y: -0.08,
                font: {
                    size: 12,
                },
            },
            hovermode: "closest",
        },
        {
            displaylogo: false,
            responsive: true,
            modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d"],
            toImageButtonOptions: {
                filename: "verbatim-community-network",
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


function renderFallbackNetworkChart(points) {
    return `
        <div class="analysis-chart-fallback">
            <p class="analysis-chart-fallback-note">Interactive charts are unavailable right now, so the community network cannot be drawn.</p>
            <p class="analysis-chart-fallback-note">${escapeHtml(String(points.length))} response point(s) were available for the network plot.</p>
        </div>
    `;
}
