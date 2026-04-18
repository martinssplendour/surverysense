import { beforeEach, describe, expect, it, vi } from "vitest";

class FakeElement {
    constructor() {
        this.hidden = false;
        this.disabled = false;
        this.innerHTML = "";
        this.textContent = "";
        this.value = "";
        this.classList = {
            add: vi.fn(),
            remove: vi.fn(),
            toggle: vi.fn(),
        };
    }
}

function installDom() {
    const elements = new Map();
    const body = {
        classList: {
            add: vi.fn(),
            remove: vi.fn(),
            toggle: vi.fn(),
        },
    };
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
    globalThis.CustomEvent = class {
        constructor(type) {
            this.type = type;
        }
    };
    return { body, elements };
}

async function loadWorkspaceHarness({ search = "", navigationType = "navigate", storedPayload = null }) {
    vi.resetModules();
    const dom = installDom();
    const storage = new Map();
    if (storedPayload) {
        storage.set("verbatim-app:last-upload-result", JSON.stringify(storedPayload));
    }

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
    globalThis.performance = {
        getEntriesByType() {
            return [{ type: navigationType }];
        },
    };
    globalThis.history = {
        replaceState: vi.fn(),
    };
    globalThis.window = {
        location: {
            search,
            pathname: "/",
            hash: "",
        },
        scrollTo: vi.fn(),
        dispatchEvent: vi.fn(),
    };

    vi.doMock("./analysis.js", () => ({
        renderAnalysisOutput: vi.fn(),
        renderAnalysisPanel: vi.fn(),
    }));
    vi.doMock("./modals.js", () => ({
        closeAnalysisGroupModal: vi.fn(),
    }));
    vi.doMock("./columnRoles.js", () => ({
        closeColumnRoleModal: vi.fn(),
    }));
    vi.doMock("./workspaceFilterBar.js", () => ({
        closeFilterModal: vi.fn(),
        openFilterModal: vi.fn(),
        renderFilterBar: vi.fn(),
    }));
    vi.doMock("./workspacePreviewTable.js", () => ({
        handlePreviewModeChange: vi.fn(),
        handlePreviewTableScroll: vi.fn(),
        handleSliderInput: vi.fn(),
        renderPreviewTable: vi.fn(),
        syncSliderRange: vi.fn(),
    }));
    vi.doMock("./workspaceModalFocus.js", () => ({
        handleDocumentKeydown: vi.fn(),
    }));
    vi.doMock("./rows.js", () => ({
        currentPreviewDataset: vi.fn(() => "analysis"),
        ensureDatasetRowCount: vi.fn(async () => {}),
        getInitialVisibleRowTarget: vi.fn(() => 50),
    }));

    const workspace = await import("./workspace.js");
    const { state } = await import("./shared.js");
    return {
        dom,
        historyReplaceState: globalThis.history.replaceState,
        state,
        storage,
        workspace,
    };
}

describe("results/workspace", () => {
    beforeEach(() => {
        vi.restoreAllMocks();
    });

    it("restores a stored payload on upload handoff reloads", async () => {
        const payload = {
            result_id: "result-123",
            filename: "survey.csv",
            transformed_column_names: ["comment", "country"],
            transformed_row_count: 3,
            analysis_metadata_column_names: ["country"],
            analysis_verbatim_column_names: ["comment"],
            analysis_column_names: ["country", "comment"],
            analysis_row_count: 3,
            transformed_preview_rows: [],
            analysis_preview_rows: [],
            available_filters: [],
        };
        const harness = await loadWorkspaceHarness({
            search: "?handoff=1",
            navigationType: "reload",
            storedPayload: payload,
        });

        await harness.workspace.loadResultsPage();

        expect(harness.state.resultId).toBe("result-123");
        expect(harness.state.analysisVerbatimColumns).toEqual(["comment"]);
        expect(harness.historyReplaceState).toHaveBeenCalledWith(null, "", "/");
    });

    it("drops stale stored results on plain reloads without a handoff token", async () => {
        const payload = {
            result_id: "result-123",
            transformed_column_names: ["comment"],
        };
        const harness = await loadWorkspaceHarness({
            search: "",
            navigationType: "reload",
            storedPayload: payload,
        });

        await harness.workspace.loadResultsPage();

        expect(harness.storage.has("verbatim-app:last-upload-result")).toBe(false);
        expect(harness.dom.body.classList.toggle).toHaveBeenCalledWith("upload-workspace-active", true);
        expect(harness.state.resultId).toBeNull();
    });
});
