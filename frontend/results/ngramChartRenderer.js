import { elements } from "./shared.js";
import { escapeHtml, normalizeValue } from "./shared/utils.js";
import { getPlotly, queueAnalysisPlotResize, resizeAnalysisPlots } from "./plotlyRuntime.js";


const MAX_ITEMS_PER_NGRAM_CHART = 10;
const MIN_NGRAM_CARD_WIDTH = 480;
const SINGLE_WORD_ROW_HEIGHT = 36;
const PHRASE_ROW_HEIGHT = 44;
const PLOT_VERTICAL_PADDING = 96;
const MIN_PLOT_HEIGHT = 260;
let ngramResizeObserver = null;


export function renderNgramFrequencyCharts(buckets, { openAnalysisNgramModal }) {
    disconnectNgramResizeObserver();
    elements.analysisChart.hidden = false;
    elements.analysisChart.innerHTML = `
        <div class="analysis-chart-copy">
            <h4 class="analysis-chart-title">Most common words and phrases in the selected responses</h4>
            <p class="analysis-chart-caption">Hover to see how often each word or phrase appears. Click a bar to open the matching responses.</p>
        </div>
        <div class="analysis-plot-grid analysis-ngram-plot-grid">
            ${buckets
                .map((bucket, index) => {
                    const label = bucket.label || `${bucket.ngram_size}-grams`;
                    const plotHeight = getNgramFigureHeight(bucket);
                    return `
                    <div class="analysis-plot-card analysis-ngram-plot-card" style="--ngram-plot-min-height: ${plotHeight}px;">
                        <h4>${escapeHtml(label)}</h4>
                        <div class="analysis-plot-surface analysis-ngram-plot-surface" id="analysis-ngram-plot-${index}"></div>
                    </div>
                `;
                })
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
    observeResizableNgramCards(plotly);
    queueAnalysisPlotResize();
}


function renderInteractiveNgramChart(plotContainer, bucket, bucketIndex, { openAnalysisNgramModal }) {
    const plotly = getPlotly();
    if (!plotly || !(plotContainer instanceof HTMLElement)) {
        return false;
    }

    const items = Array.isArray(bucket.items) ? bucket.items.slice(0, MAX_ITEMS_PER_NGRAM_CHART) : [];
    const label = bucket.label || `${bucket.ngram_size}-grams`;
    const ngramSize = Number(bucket.ngram_size || 0);
    const itemTypeLabel = ngramSize === 1 ? "word" : "phrase";
    const tickLabels = items.map((item) => formatNgramTickLabel(item.term || "", ngramSize));
    const leftMargin = calculateNgramLeftMargin(tickLabels, ngramSize);
    const figureHeight = getNgramFigureHeight(bucket);
    plotContainer.style.minHeight = `${figureHeight}px`;
    const colorsBySize = {
        1: "#2477F8",
        2: "#c7923f",
        3: "#b7685f",
    };

    const plotPromise = plotly.newPlot(
        plotContainer,
        [
            {
                type: "bar",
                orientation: "h",
                y: tickLabels,
                x: items.map((item) => Number(item.count || 0)),
                text: items.map((item) => normalizeValue(item.term || "")),
                marker: {
                    color: colorsBySize[ngramSize] || "#7a6b5e",
                },
                customdata: items.map((item, itemIndex) => [
                    normalizeValue(item.term || ""),
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
            height: figureHeight,
            autosize: true,
            margin: {
                t: 18,
                r: 22,
                b: 56,
                l: leftMargin,
            },
            paper_bgcolor: "rgba(0, 0, 0, 0)",
            plot_bgcolor: "rgba(255, 250, 242, 0.72)",
            font: {
                family: "\"Segoe UI\", Aptos, sans-serif",
                color: "#3d352d",
                size: 12,
            },
            bargap: 0.26,
            xaxis: {
                title: {
                    text: `Number of times the ${itemTypeLabel} appears`,
                },
                gridcolor: "rgba(89, 68, 42, 0.1)",
                zeroline: false,
            },
            yaxis: {
                automargin: true,
                autorange: "reversed",
                tickfont: {
                    size: 12,
                },
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


function disconnectNgramResizeObserver() {
    if (ngramResizeObserver) {
        ngramResizeObserver.disconnect();
        ngramResizeObserver = null;
    }
}


function observeResizableNgramCards(plotly) {
    if (typeof ResizeObserver === "undefined") {
        return;
    }

    ngramResizeObserver = new ResizeObserver((entries) => {
        entries.forEach((entry) => {
            const plotSurface = entry.target.querySelector(".analysis-ngram-plot-surface");
            if (!(plotSurface instanceof HTMLElement)) {
                return;
            }
            try {
                const width = Math.max(MIN_NGRAM_CARD_WIDTH - 32, Math.floor(plotSurface.clientWidth));
                const height = Math.max(MIN_PLOT_HEIGHT, Math.floor(plotSurface.clientHeight));
                if (typeof plotly.relayout === "function") {
                    plotly.relayout(plotSurface, { width, height });
                } else {
                    plotly.Plots.resize(plotSurface);
                }
            } catch (_error) {
                // Ignore resize noise while Plotly is still mounting.
            }
        });
    });

    elements.analysisChart.querySelectorAll(".analysis-ngram-plot-card").forEach((card) => {
        ngramResizeObserver.observe(card);
    });
    resizeAnalysisPlots();
}


function getNgramFigureHeight(bucket) {
    const items = Array.isArray(bucket.items) ? bucket.items.slice(0, MAX_ITEMS_PER_NGRAM_CHART) : [];
    const ngramSize = Number(bucket.ngram_size || 0);
    const rowHeight = ngramSize > 1 ? PHRASE_ROW_HEIGHT : SINGLE_WORD_ROW_HEIGHT;
    return Math.max(MIN_PLOT_HEIGHT, PLOT_VERTICAL_PADDING + items.length * rowHeight);
}


function formatNgramTickLabel(value, ngramSize) {
    const words = normalizeValue(value).split(/\s+/).filter(Boolean);
    if (!words.length) {
        return "Untitled";
    }
    if (ngramSize <= 1 || words.length === 1) {
        return truncatePlotLabelLine(words.join(" "), 18);
    }

    const maxLineLength = ngramSize >= 3 ? 16 : 18;
    const firstLine = truncatePlotLabelLine(words.slice(0, Math.ceil(words.length / 2)).join(" "), maxLineLength);
    const secondLine = truncatePlotLabelLine(words.slice(Math.ceil(words.length / 2)).join(" "), maxLineLength);
    return secondLine ? `${firstLine}<br>${secondLine}` : firstLine;
}


function truncatePlotLabelLine(value, maxLineLength) {
    const normalized = normalizeValue(value);
    if (!normalized) {
        return "";
    }
    if (normalized.length <= maxLineLength) {
        return normalized;
    }
    return `${normalized.slice(0, Math.max(1, maxLineLength - 3)).trimEnd()}...`;
}


function calculateNgramLeftMargin(tickLabels, ngramSize) {
    const longestLineLength = tickLabels.reduce((maximum, label) => {
        const lineLengths = String(label)
            .split("<br>")
            .map((line) => line.length);
        return Math.max(maximum, ...lineLengths);
    }, 0);
    const minimumMargin = ngramSize > 1 ? 124 : 96;
    return Math.min(220, Math.max(minimumMargin, Math.round(longestLineLength * 7.2 + 34)));
}
