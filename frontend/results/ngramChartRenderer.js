import { elements } from "./shared.js";
import { wrapPlotLabel } from "./shared/utils.js";
import { getPlotly, queueAnalysisPlotResize } from "./plotlyRuntime.js";


export function renderNgramFrequencyCharts(buckets, { openAnalysisNgramModal }) {
    elements.analysisChart.hidden = false;
    elements.analysisChart.innerHTML = `
        <div class="analysis-chart-copy">
            <h4 class="analysis-chart-title">Most common words and phrases in the selected responses</h4>
            <p class="analysis-chart-caption">Hover to see how often each word or phrase appears. Click a bar to open the matching responses.</p>
        </div>
        <div class="analysis-plot-grid">
            ${buckets
                .map((_bucket, index) => `
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
        renderInteractiveNgramChart(plotContainer, bucket, index, { openAnalysisNgramModal });
    });
    queueAnalysisPlotResize();
}


function renderInteractiveNgramChart(plotContainer, bucket, bucketIndex, { openAnalysisNgramModal }) {
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
                        openAnalysisNgramModal(bucketIndex, itemIndex);
                    }
                });
            }
        });
    }

    return true;
}
