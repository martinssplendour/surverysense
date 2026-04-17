// Handles CSV file selection, drag-and-drop, and upload submission on the upload page.
(function () {
const RESULT_STORAGE_KEY = "verbatim-app:last-upload-result";

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

    // Add the "is-dragover" highlight class while a file is dragged over the dropzone.
    ["dragenter", "dragover"].forEach((eventName) => {
        elements.dropzone.addEventListener(eventName, (event) => {
            event.preventDefault();
            elements.dropzone.classList.add("is-dragover");
        });
    });

    // Remove the highlight and handle the dropped file when the drag ends.
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
    showStatus("neutral", "Processing CSV...");
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
            // Store the API payload in sessionStorage so the results page can read it after navigation.
            sessionStorage.setItem(RESULT_STORAGE_KEY, JSON.stringify(payload));
        } catch (error) {
            console.warn(
                "[Verbatim App] Failed to cache the processed result in session storage; upload succeeded but the dashboard handoff cannot continue.",
                error,
            );
            showStatus("error", "Unable to save results — browser storage may be full.");
            setBusyState(false);
            return;
        }
        // Navigate to the root with ?handoff=1 so the results page knows this is a fresh upload,
        // not a browser reload that should clear the stored result.
        window.location.assign("/?handoff=1");
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
        elements.processButton.innerHTML = '<span class="upload-button-content"><span class="upload-button-spinner" aria-hidden="true"></span><span>Processing...</span></span>';
        return;
    }
    elements.processButton.textContent = "Process File";
}

function showStatus(kind, message) {
    elements.statusMessage.textContent = message;
    elements.statusMessage.className = `status-message status-${kind}`;
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

})();
