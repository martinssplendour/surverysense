const RESULT_STORAGE_KEY = "verbatim-app:last-upload-result";

const state = {
    file: null,
};

const elements = {
    uploadForm: document.getElementById("upload-form"),
    dropzone: document.getElementById("dropzone"),
    fileInput: document.getElementById("csv-file"),
    fileLabel: document.getElementById("file-label"),
    fileMeta: document.getElementById("file-meta"),
    chooseFileButton: document.getElementById("choose-file-btn"),
    processButton: document.getElementById("process-btn"),
    statusMessage: document.getElementById("status-message"),
};

bindEvents();

function bindEvents() {
    elements.chooseFileButton.addEventListener("click", () => {
        elements.fileInput.click();
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

function setFile(file) {
    state.file = file;

    if (!file) {
        elements.fileInput.value = "";
        elements.fileLabel.textContent = "Select a CSV file or drag it here";
        elements.fileMeta.textContent = "Accepted format: .csv";
        elements.processButton.disabled = true;
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

    setBusyState(true);
    showStatus("neutral", "Processing CSV and preparing the results page...");

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

        sessionStorage.setItem(RESULT_STORAGE_KEY, JSON.stringify(payload));
        window.location.assign("/results");
    } catch (error) {
        const message = error instanceof Error ? error.message : "Processing failed.";
        showStatus("error", message);
        setBusyState(false);
    }
}

function setBusyState(isBusy) {
    elements.processButton.disabled = isBusy || !state.file;
    elements.chooseFileButton.disabled = isBusy;
    elements.fileInput.disabled = isBusy;
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
