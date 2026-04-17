(function () {
const RESULT_STORAGE_KEY = "verbatim-app:last-upload-result";
const RESULT_HANDOFF_MAX_ATTEMPTS = 20;
const RESULT_HANDOFF_RETRY_MS = 100;
let uploadElapsedTimer = null;
let uploadStartedAt = 0;

const state = {
    file: null,
    aiAvailable: true,
    architectRowCount: 25,
    diagnosticMode: "ai",
};

const elements = {
    uploadForm: document.getElementById("upload-form"),
    dropzone: document.getElementById("dropzone"),
    fileInput: document.getElementById("csv-file"),
    fileLabel: document.getElementById("file-label"),
    fileMeta: document.getElementById("file-meta"),
    processButton: document.getElementById("process-btn"),
    statusMessage: document.getElementById("status-message"),
};

bindEvents();
loadDiagnosticConfig();

function bindEvents() {
    window.addEventListener("verbatim:upload-reset", () => {
        setFile(null);
    });

    elements.fileInput.addEventListener("change", () => {
        const [file] = elements.fileInput.files;
        setFile(file ?? null);
    });

    elements.uploadForm.addEventListener("submit", handleSubmit);

    ["dragenter", "dragover"].forEach((eventName) => {
        elements.dropzone.addEventListener(eventName, (event) => {
            event.preventDefault();
            elements.dropzone.classList.add("is-dragover");
        });
    });

    ["dragleave", "dragend", "drop"].forEach((eventName) => {
        elements.dropzone.addEventListener(eventName, (event) => {
            event.preventDefault();
            elements.dropzone.classList.remove("is-dragover");
        });
    });

    elements.dropzone.addEventListener("drop", (event) => {
        const [file] = event.dataTransfer?.files ?? [];
        setFile(file ?? null);
    });
}

async function loadDiagnosticConfig() {
    try {
        const response = await fetch("/diagnostic-config");
        if (response.status === 401) {
            window.location.assign("/login");
            return;
        }
        const payload = await parseJson(response);
        if (!response.ok) {
            throw new Error(payload.detail || "Unable to load diagnosis options.");
        }
        state.aiAvailable = Boolean(payload.ai_available);
        state.architectRowCount = Number(payload.architect_row_count) || 25;
        state.diagnosticMode = payload.default_diagnostic_mode || "ai";
    } catch {
        state.aiAvailable = true;
        state.architectRowCount = 25;
        state.diagnosticMode = "ai";
    }
    console.info(
        `[Verbatim App] Diagnosis workflow ready: ${formatDiagnosticModeLabel(state.diagnosticMode)} using first ${state.architectRowCount} rows.`,
    );
}

function setFile(file) {
    state.file = file;

    if (!file) {
        elements.fileInput.value = "";
        elements.fileLabel.textContent = "Select a CSV file or drag it here";
        elements.fileMeta.textContent = "Accepted format: .csv";
        elements.processButton.disabled = true;
        elements.processButton.innerHTML = "Process File";
        showStatus("neutral", "Waiting for a CSV upload.");
        return;
    }

    const isCsv = file.name.toLowerCase().endsWith(".csv");
    elements.fileLabel.textContent = file.name;
    elements.fileMeta.textContent = `${formatBytes(file.size)} ready to process`;
    elements.processButton.disabled = !isCsv;

    if (!isCsv) {
        showStatus("error", "Only .csv files are supported.");
        return;
    }

    showStatus("neutral", "File selected. Process when ready.");
}

async function handleSubmit(event) {
    event.preventDefault();

    if (!state.file) {
        showStatus("error", "Choose a CSV file first.");
        return;
    }

    const formData = new FormData();
    formData.append("file", state.file);
    formData.append("diagnostic_mode", state.diagnosticMode);

    setBusyState(true);
    showStatus("neutral", `Processing CSV with ${formatDiagnosticModeLabel(state.diagnosticMode)}...`);
    console.info(
        `[Verbatim App] Starting upload with ${formatDiagnosticModeLabel(state.diagnosticMode)} for ${state.file.name}.`,
    );

    try {
        const response = await fetch("/upload-ingest", {
            method: "POST",
            body: formData,
        });
        if (response.status === 401) {
            sessionStorage.removeItem(RESULT_STORAGE_KEY);
            window.location.assign("/login");
            return;
        }
        const payload = await parseJson(response);

        if (!response.ok) {
            throw new Error(payload.detail || "The API request failed.");
        }

        try {
            sessionStorage.setItem(RESULT_STORAGE_KEY, JSON.stringify(payload));
        } catch (error) {
            console.warn("[Verbatim App] Unable to cache processed result in session storage.", error);
        }
        console.info(
            `[Verbatim App] Processing finished with ${payload.manifest?.diagnostic_source || state.diagnosticMode} manifest generation.`,
        );
        setBusyState(false);
        showStatus("neutral", "File processed.");
        handoffProcessedResult(payload);
    } catch (error) {
        const message = error instanceof Error ? error.message : "Processing failed.";
        showStatus("error", message);
        setBusyState(false);
    }
}

function setBusyState(isBusy) {
    elements.processButton.disabled = isBusy || !state.file;
    elements.fileInput.disabled = isBusy;
    if (isBusy) {
        uploadStartedAt = Date.now();
        elements.processButton.innerHTML = '<span class="upload-button-content"><span class="upload-button-spinner" aria-hidden="true"></span><span>Processing...</span></span>';
        updateElapsedStatus();
        if (uploadElapsedTimer) {
            window.clearInterval(uploadElapsedTimer);
        }
        uploadElapsedTimer = window.setInterval(updateElapsedStatus, 1000);
        return;
    }

    elements.processButton.textContent = "Process File";
    if (uploadElapsedTimer) {
        window.clearInterval(uploadElapsedTimer);
        uploadElapsedTimer = null;
    }
    uploadStartedAt = 0;
}

function showStatus(kind, message) {
    elements.statusMessage.textContent = message;
    elements.statusMessage.className = `status-message status-${kind}`;
}

function updateElapsedStatus() {
    if (!uploadStartedAt) {
        return;
    }
    const elapsedSeconds = Math.max(0, Math.floor((Date.now() - uploadStartedAt) / 1000));
    const minutes = Math.floor(elapsedSeconds / 60);
    const seconds = elapsedSeconds % 60;
    const elapsedLabel = `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")} elapsed`;
    showStatus("neutral", `Processing CSV with ${formatDiagnosticModeLabel(state.diagnosticMode)}... ${elapsedLabel}`);
}

function handoffProcessedResult(payload, attempt = 0) {
    if (typeof window.verbatimApplyProcessedResult === "function") {
        window.verbatimApplyProcessedResult(payload);
        return;
    }

    window.dispatchEvent(new CustomEvent("verbatim:result-ready", { detail: payload }));

    if (typeof window.verbatimApplyProcessedResult === "function") {
        window.verbatimApplyProcessedResult(payload);
        return;
    }

    if (attempt >= RESULT_HANDOFF_MAX_ATTEMPTS) {
        window.location.assign("/");
        return;
    }

    window.setTimeout(() => {
        handoffProcessedResult(payload, attempt + 1);
    }, RESULT_HANDOFF_RETRY_MS);
}

async function parseJson(response) {
    try {
        return await response.json();
    } catch {
        return {};
    }
}

function formatBytes(bytes) {
    if (!Number.isFinite(bytes) || bytes <= 0) {
        return "0 B";
    }

    const sizes = ["B", "KB", "MB", "GB"];
    const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), sizes.length - 1);
    const value = bytes / (1024 ** exponent);
    return `${value.toFixed(value >= 10 || exponent === 0 ? 0 : 1)} ${sizes[exponent]}`;
}

function formatDiagnosticModeLabel(mode) {
    return mode === "rule_based" ? "rule-based diagnosis" : "AI diagnosis";
}
})();
