import { beforeEach, describe, expect, it, vi } from "vitest";

class FakeElement {
    constructor() {
        this.hidden = false;
        this.disabled = false;
        this.innerHTML = "";
        this.textContent = "";
        this.title = "";
        this.value = "";
        this.dataset = {};
        this.tabIndex = 0;
        this.className = "";
        this.classList = {
            add: vi.fn(),
            remove: vi.fn(),
            toggle: vi.fn(),
        };
    }

    querySelectorAll() {
        return [];
    }

    setAttribute(name, value) {
        this[name] = String(value);
    }

    closest() {
        return null;
    }
}

class FakeSelectElement extends FakeElement {}
class FakeButtonElement extends FakeElement {}

function installDom() {
    const elements = new Map();
    const body = {
        classList: {
            add: vi.fn(),
            remove: vi.fn(),
            toggle: vi.fn(),
        },
    };
    globalThis.HTMLElement = FakeElement;
    globalThis.HTMLSelectElement = FakeSelectElement;
    globalThis.HTMLButtonElement = FakeButtonElement;
    globalThis.document = {
        body,
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

async function loadAnalysisHarness({ fetchImpl }) {
    vi.resetModules();
    const dom = installDom();
    const storage = new Map();
    const locationAssign = vi.fn();
    const scrollTo = vi.fn();
    const updateWorkspaceVisibility = vi.fn();
    const closeAnalysisGroupModal = vi.fn();
    const handleMissingResultState = vi.fn();
    const renderFilterBar = vi.fn();

    globalThis.fetch = fetchImpl;
    globalThis.window = {
        location: { assign: locationAssign },
        scrollTo,
    };
    globalThis.sessionStorage = {
        getItem(key) {
            return storage.has(key) ? storage.get(key) : null;
        },
        setItem(key, value) {
            storage.set(key, String(value));
        },
        removeItem(key) {
            storage.delete(key);
        },
    };

    vi.doMock("./charts.js", () => ({
        clearAnalysisChart: vi.fn(),
        renderAnalysisChart: vi.fn(),
        renderNgramCharts: vi.fn(),
    }));
    vi.doMock("./charts/export.js", () => ({
        displayAnalysisExportFormat: (value) => String(value || "").toUpperCase(),
        normalizeAnalysisExportFormat: (value) => value || "pdf",
    }));
    vi.doMock("./data/rows.js", () => ({
        parseJson: async (response) => response.json(),
    }));

    const analysis = await import("./analysis.js");
    const { state } = await import("./shared.js");
    analysis.configureResultsAnalysis({
        closeAnalysisGroupModal,
        handleMissingResultState,
        renderFilterBar,
        updateWorkspaceVisibility,
    });
    return {
        analysis,
        closeAnalysisGroupModal,
        dom,
        handleMissingResultState,
        locationAssign,
        scrollTo,
        state,
        storage,
        updateWorkspaceVisibility,
    };
}

function createJsonResponse({ ok, status, payload }) {
    return {
        ok,
        status,
        async json() {
            return payload;
        },
    };
}

describe("results/analysis", () => {
    beforeEach(() => {
        vi.restoreAllMocks();
    });

    it("stores a successful analysis response and switches to the results workspace", async () => {
        const payload = {
            ok: true,
            result_id: "result-123",
            model_key: "community",
            text_column_name: "comment",
            filtered_row_count: 3,
            valid_document_count: 3,
            original_response_count: 2,
            skipped_document_count: 0,
            groups: [{ group_id: "0", label: "Support", count: 3, share: 1, examples: [] }],
            ngram_buckets: [],
            scatter_points: [],
        };
        const fetchMock = vi.fn(async () => createJsonResponse({ ok: true, status: 200, payload }));
        const harness = await loadAnalysisHarness({ fetchImpl: fetchMock });

        harness.state.resultId = "result-123";
        harness.state.analysisVerbatimColumns = ["comment"];
        harness.state.selectedAnalysisColumn = "comment";
        harness.state.selectedAnalysisModel = "community";
        harness.state.activeFilters = { country: ["UK"] };
        harness.state.currentWorkspace = "analysis";

        await harness.analysis.runAnalysis({ scrollIntoView: true });

        expect(fetchMock).toHaveBeenCalledTimes(1);
        expect(fetchMock.mock.calls[0][0]).toBe("/run-analysis/result-123");
        expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
            model_key: "community",
            text_column_name: "comment",
            filters: { country: ["UK"] },
        });
        expect(harness.closeAnalysisGroupModal).toHaveBeenCalledTimes(1);
        expect(harness.state.analysisResult).toEqual(payload);
        expect(harness.state.currentWorkspace).toBe("analysis-results");
        expect(harness.updateWorkspaceVisibility).toHaveBeenCalledTimes(1);
        expect(harness.scrollTo).toHaveBeenCalledWith({ top: 0, behavior: "smooth" });
        const subtitle = harness.dom.elements.get("analysis-results-subtitle");
        expect(subtitle.innerHTML).toContain("comment");
        expect(subtitle.innerHTML).toContain("2");
    });

    it("hands missing result state back to the workspace layer on 404", async () => {
        const fetchMock = vi.fn(async () => createJsonResponse({
            ok: false,
            status: 404,
            payload: { detail: "The result expired." },
        }));
        const harness = await loadAnalysisHarness({ fetchImpl: fetchMock });

        harness.state.resultId = "result-123";
        harness.state.analysisVerbatimColumns = ["comment"];
        harness.state.selectedAnalysisColumn = "comment";
        harness.state.selectedAnalysisModel = "community";

        await harness.analysis.runAnalysis();

        expect(harness.handleMissingResultState).toHaveBeenCalledWith("The result expired.");
        expect(harness.state.analysisResult).toBeNull();
        expect(harness.state.analysisRunning).toBe(false);
    });

    it("stores a structured failure result when the analysis request fails", async () => {
        const fetchMock = vi.fn(async () => createJsonResponse({
            ok: false,
            status: 500,
            payload: { detail: "Backend unavailable." },
        }));
        const harness = await loadAnalysisHarness({ fetchImpl: fetchMock });

        harness.state.resultId = "result-123";
        harness.state.analysisVerbatimColumns = ["comment"];
        harness.state.selectedAnalysisColumn = "comment";
        harness.state.selectedAnalysisModel = "ngrams";

        await harness.analysis.runAnalysis();

        expect(harness.state.analysisResult.ok).toBe(false);
        expect(harness.state.analysisResult.error).toBe("Backend unavailable.");
        expect(harness.state.analysisResult.model_key).toBe("ngrams");
        expect(harness.state.currentWorkspace).toBe("analysis-results");
        expect(harness.updateWorkspaceVisibility).toHaveBeenCalledTimes(1);
    });
});
