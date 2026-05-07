import { beforeEach, describe, expect, it, vi } from "vitest";


class FakeElement {
    constructor() {
        this.textContent = "";
    }

    querySelector() {
        return null;
    }
}


function installDom() {
    const elements = new Map();
    globalThis.document = {
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
    return elements;
}


async function loadRequestHarness() {
    vi.resetModules();
    const domElements = installDom();
    vi.doMock("./generatedCharts.js", () => ({
        captureRenderedAnalysisCharts: vi.fn(async () => []),
    }));
    const { elements, state } = await import("../../shared.js");
    const { buildAnalysisExportResultPayload, requestAnalysisReportBlob } = await import("./request.js");
    return {
        buildAnalysisExportResultPayload,
        domElements,
        elements,
        requestAnalysisReportBlob,
        state,
    };
}


describe("results/charts/export/request", () => {
    beforeEach(() => {
        vi.restoreAllMocks();
    });

    it("keeps the analyzed column name in the export analysis result payload", async () => {
        const harness = await loadRequestHarness();
        harness.state.selectedAnalysisColumn = "comment__idx_2";
        harness.state.analysisResult = {
            ok: true,
            result_id: "abc123",
            model_key: "community",
            model_label: "Community Detection",
            filtered_row_count: 100,
            groups: [],
            ngram_buckets: [],
        };

        expect(harness.buildAnalysisExportResultPayload().text_column_name).toBe("comment__idx_2");
    });

    it("sends the restored analyzed column name before backend report generation", async () => {
        const harness = await loadRequestHarness();
        harness.state.resultId = "abc123";
        harness.state.response = { filename: "survey.csv" };
        harness.state.selectedAnalysisColumn = "comment";
        harness.state.analysisResult = {
            ok: true,
            result_id: "abc123",
            model_key: "community",
            model_label: "Community Detection",
            filtered_row_count: 100,
            groups: [],
            ngram_buckets: [],
        };
        harness.elements.analysisResultsSubtitle.textContent = "Question: comment Responses: 100";
        const fetchImpl = vi.fn(async () => ({
            ok: true,
            status: 200,
            headers: { get: () => "attachment; filename=\"survey-community-detection-report.pdf\"" },
            blob: async () => new Blob(["pdf"]),
        }));
        globalThis.fetch = fetchImpl;

        await harness.requestAnalysisReportBlob({
            format: "pdf",
            callbacks: {
                parseJson: vi.fn(),
                handleMissingResultState: vi.fn(),
            },
        });

        const requestBody = JSON.parse(fetchImpl.mock.calls[0][1].body);
        expect(requestBody.analysis_result.text_column_name).toBe("comment");
    });
});
