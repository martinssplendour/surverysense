import { beforeEach, describe, expect, it, vi } from "vitest";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";

const uploadScript = fs.readFileSync(path.resolve(process.cwd(), "upload.js"), "utf8");

function createElement() {
    return {
        disabled: false,
        hidden: false,
        textContent: "",
        innerHTML: "",
        value: "",
        files: [],
        className: "",
        listeners: new Map(),
        classList: {
            add: vi.fn(),
            remove: vi.fn(),
        },
        addEventListener(type, handler) {
            this.listeners.set(type, handler);
        },
        dispatch(type, event = {}) {
            const handler = this.listeners.get(type);
            if (handler) {
                return handler(event);
            }
            return undefined;
        },
    };
}

function buildHarness(overrides = {}) {
    const elements = {
        "upload-form": createElement(),
        dropzone: createElement(),
        "csv-file": createElement(),
        "file-label": createElement(),
        "file-meta": createElement(),
        "process-btn": createElement(),
        "status-message": createElement(),
    };

    const storage = new Map();
    const uploadPayload = {
        result_id: "result-123",
        transformed_column_names: ["comment"],
        transformed_row_count: 5,
        analysis_verbatim_column_names: ["comment"],
    };
    const locationAssign = vi.fn();
    const fetchMock = vi.fn(async (url) => {
        if (url === "/diagnostic-config") {
            return {
                status: 200,
                ok: true,
                json: async () => ({
                    ai_available: true,
                    architect_row_count: 25,
                    default_diagnostic_mode: "ai",
                }),
            };
        }

        if (url === "/upload-ingest") {
            return {
                status: 200,
                ok: true,
                json: async () => uploadPayload,
            };
        }

        throw new Error(`Unexpected fetch: ${url}`);
    });

    const windowListeners = new Map();
    const hasLocationAssignOverride = Object.prototype.hasOwnProperty.call(overrides, "locationAssign");

    const context = {
        console,
        fetch: overrides.fetch ?? fetchMock,
        FormData: class {
            constructor() {
                this.values = [];
            }
            append(key, value) {
                this.values.push([key, value]);
            }
        },
        CustomEvent: class {
            constructor(type, init = {}) {
                this.type = type;
                this.detail = init.detail;
            }
        },
        document: {
            getElementById(id) {
                return elements[id] ?? null;
            },
        },
        sessionStorage: {
            getItem(key) {
                return storage.has(key) ? storage.get(key) : null;
            },
            setItem(key, value) {
                storage.set(key, String(value));
            },
            removeItem(key) {
                storage.delete(key);
            },
        },
        window: {
            addEventListener(type, handler) {
                windowListeners.set(type, handler);
            },
            dispatchEvent(event) {
                const handler = windowListeners.get(event.type);
                if (handler) {
                    handler(event);
                }
            },
            location: {
                assign: hasLocationAssignOverride ? overrides.locationAssign : locationAssign,
            },
            clearInterval: vi.fn(),
            setInterval: vi.fn(() => 1),
            setTimeout: (fn) => {
                fn();
                return 1;
            },
        },
        setTimeout: (fn) => {
            fn();
            return 1;
        },
        clearTimeout: vi.fn(),
    };
    context.globalThis = context;

    vm.runInNewContext(uploadScript, context, { filename: "upload.js" });

    return {
        context,
        elements,
        storage,
        uploadPayload,
        locationAssign,
        fetchMock,
    };
}

describe("upload handoff", () => {
    beforeEach(() => {
        vi.restoreAllMocks();
    });

    it("navigates to the handoff route after upload completes", async () => {
        const harness = buildHarness();
        const fileInput = harness.elements["csv-file"];
        const uploadForm = harness.elements["upload-form"];

        fileInput.files = [{ name: "bq-results.csv", size: 1024 }];
        fileInput.dispatch("change");

        await uploadForm.dispatch("submit", {
            preventDefault() {},
        });

        expect(harness.storage.get("verbatim-app:last-upload-result")).toBe(JSON.stringify(harness.uploadPayload));
        expect(harness.locationAssign).toHaveBeenCalledWith("/?handoff=1");
    });

    it("uses the same navigation handoff path every time", async () => {
        const harness = buildHarness();
        const fileInput = harness.elements["csv-file"];
        const uploadForm = harness.elements["upload-form"];

        fileInput.files = [{ name: "bq-results.csv", size: 1024 }];
        fileInput.dispatch("change");

        await uploadForm.dispatch("submit", {
            preventDefault() {},
        });

        expect(harness.locationAssign).toHaveBeenCalledWith("/?handoff=1");
    });
});
