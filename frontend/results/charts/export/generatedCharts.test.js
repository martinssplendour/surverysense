import { beforeEach, describe, expect, it, vi } from "vitest";


class FakeElement {
    constructor() {
        this.children = [];
        this.hidden = false;
        this.innerHTML = "";
        this.layout = null;
        this.data = null;
        this.style = {};
        this.textContent = "";
    }

    appendChild(child) {
        this.children.push(child);
        child.parentElement = this;
        return child;
    }

    remove() {
        if (!this.parentElement) {
            return;
        }
        this.parentElement.children = this.parentElement.children.filter((child) => child !== this);
        this.parentElement = null;
    }

    querySelector() {
        return null;
    }

    querySelectorAll() {
        return [];
    }
}


function installDom() {
    const elements = new Map();
    const body = new FakeElement();
    globalThis.HTMLElement = FakeElement;
    globalThis.document = {
        body,
        createElement() {
            return new FakeElement();
        },
        getElementById(id) {
            if (!elements.has(id)) {
                elements.set(id, new FakeElement());
            }
            return elements.get(id);
        },
        querySelector() {
            return new FakeElement();
        },
    };
    return { body, elements };
}


async function loadGeneratedChartsHarness() {
    vi.resetModules();
    const dom = installDom();
    const plotly = {
        newPlot: vi.fn(async (element, data, layout) => {
            element.data = data;
            element.layout = layout;
        }),
        purge: vi.fn(),
        toImage: vi.fn(async () => "data:image/png;base64,chart"),
    };
    globalThis.window = { Plotly: plotly };

    const { state } = await import("../../shared.js");
    const { captureRenderedAnalysisCharts } = await import("./generatedCharts.js");
    return { captureRenderedAnalysisCharts, dom, plotly, state };
}


describe("results/charts/export/generatedCharts", () => {
    beforeEach(() => {
        vi.restoreAllMocks();
    });

    it("generates export-only Plotly charts for n-gram buckets", async () => {
        const harness = await loadGeneratedChartsHarness();
        harness.state.analysisResult = {
            model_key: "ngrams",
            model_label: "N-grams",
            text_column_name: "comments",
            groups: [],
            ngram_buckets: [
                {
                    label: "One-word terms",
                    ngram_size: 1,
                    items: [
                        { term: "search", count: 12, document_count: 10 },
                        { term: "resources", count: 8, document_count: 7 },
                    ],
                },
                {
                    label: "Two-word phrases",
                    ngram_size: 2,
                    items: [
                        { term: "lesson planning", count: 6, document_count: 5 },
                    ],
                },
                {
                    label: "Three-word phrases",
                    ngram_size: 3,
                    items: [
                        { term: "easy lesson planning", count: 4, document_count: 4 },
                    ],
                },
            ],
        };
        harness.dom.elements.get("analysis-chart").querySelector = () => ({
            textContent: "Click a row to open the matching responses.",
        });

        const charts = await harness.captureRenderedAnalysisCharts();

        expect(charts).toEqual([
            {
                title: "One-word terms",
                caption: "",
                image_data_url: "data:image/png;base64,chart",
            },
            {
                title: "Two-word phrases",
                caption: "",
                image_data_url: "data:image/png;base64,chart",
            },
            {
                title: "Three-word phrases",
                caption: "",
                image_data_url: "data:image/png;base64,chart",
            },
        ]);
        expect(harness.plotly.newPlot).toHaveBeenCalledTimes(6);
        expect(harness.plotly.toImage).toHaveBeenCalledTimes(3);
        expect(harness.plotly.purge).toHaveBeenCalledTimes(6);
        expect(harness.plotly.newPlot.mock.calls[0][2].height).toBe(290);
        expect(harness.plotly.newPlot.mock.calls[0][2].bargap).toBe(0.12);
        expect(harness.plotly.newPlot.mock.calls[0][2].yaxis.showticklabels).toBe(false);
        expect(harness.plotly.newPlot.mock.calls[2][2].height).toBe(216);
        expect(harness.plotly.newPlot.mock.calls[4][2].height).toBe(216);
        expect(harness.plotly.newPlot.mock.calls[3][2].yaxis.tickfont.size).toBe(19);
        expect(harness.plotly.newPlot.mock.calls[5][2].yaxis.tickfont.size).toBe(19);
        expect(harness.plotly.newPlot.mock.calls[5][2].margin.b).toBeGreaterThanOrEqual(112);
        expect(harness.plotly.newPlot.mock.calls[5][2].xaxis.title.text).toBe("Number of occurrences");
    });

    it("generates wrapped larger export-only Plotly charts for grouped themes", async () => {
        const harness = await loadGeneratedChartsHarness();
        harness.state.analysisResult = {
            model_key: "community",
            model_label: "Community Detection",
            text_column_name: "comments",
            groups: [
                {
                    label: "Extremely Long Theme Name That Should Never Spill Onto Three Lines",
                    count: 99,
                    share: 0.4,
                    is_noise: false,
                },
                {
                    label: "Another Long Theme Name That Needs Better Slide Legibility",
                    count: 86,
                    share: 0.3,
                    is_noise: false,
                },
            ],
            ngram_buckets: [],
        };

        const charts = await harness.captureRenderedAnalysisCharts();

        expect(charts).toEqual([
            {
                title: "Community Detection distribution",
                caption: "",
                image_data_url: "data:image/png;base64,chart",
            },
        ]);
        expect(harness.plotly.newPlot).toHaveBeenCalledTimes(2);
        expect(harness.plotly.newPlot.mock.calls[0][1][0].y[0]).toContain("<br>");
        expect(harness.plotly.newPlot.mock.calls[0][1][0].y[0].split("<br>")).toHaveLength(2);
        expect(harness.plotly.newPlot.mock.calls[0][2].height).toBe(270);
        expect(harness.plotly.newPlot.mock.calls[0][2].bargap).toBe(0.12);
        expect(harness.plotly.newPlot.mock.calls[0][2].yaxis.showticklabels).toBe(false);
        expect(harness.plotly.newPlot.mock.calls[0][2].annotations).toHaveLength(4);
        expect(harness.plotly.newPlot.mock.calls[0][2].annotations[0].yshift).toBe(10);
        expect(harness.plotly.newPlot.mock.calls[0][2].annotations[1].yshift).toBe(-10);
        expect(harness.plotly.newPlot.mock.calls[0][1][0].textfont.size).toBe(19);
        expect(harness.plotly.newPlot.mock.calls[0][2].yaxis.tickfont.size).toBe(19);
        expect(harness.plotly.newPlot.mock.calls[0][2].xaxis.tickfont.size).toBe(19);
        expect(harness.plotly.newPlot.mock.calls[1][2].margin.l).toBeGreaterThanOrEqual(404);
        expect(harness.plotly.newPlot.mock.calls[1][2].yaxis.tickfont.size).toBe(19);
    });
});
