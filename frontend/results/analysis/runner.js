import { RESULT_STORAGE_KEY, state } from "../shared.js";
import { displayAnalysisMode } from "../shared/utils.js";
import { parseJson } from "../data/rows.js";
import { resetDatasetRows } from "../data/rowsDatasetState.js";
import { emit } from "../events/bus.js";
import { closeAnalysisGroupModal } from "../modals.js";
import {
    renderAnalysisControls,
    renderAnalysisMessage,
    renderAnalysisOutput,
} from "./render.js";

let activeAnalysisAbortController = null;

/**
 * Updates the selected analysis column from the column select control.
 *
 * @param {Event} event Select change event.
 * @returns {void}
 */
export function handleAnalysisColumnChange(event) {
    const target = event.target;
    if (!(target instanceof HTMLSelectElement)) {
        return;
    }
    state.selectedAnalysisColumn = target.value;
    state.analysisResult = null;
    renderAnalysisControls();
    renderAnalysisOutput();
}

/**
 * Updates the selected analysis model from a method button click.
 *
 * @param {Event} event Click event from the analysis method container.
 * @returns {void}
 */
export function handleAnalysisMethodClick(event) {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
        return;
    }
    const methodButton = target.closest("[data-model-key]");
    if (!(methodButton instanceof HTMLElement)) {
        return;
    }
    const modelKey = methodButton.dataset.modelKey || "community";
    if (modelKey === state.selectedAnalysisModel) {
        return;
    }
    state.selectedAnalysisModel = modelKey;
    state.analysisResult = null;
    renderAnalysisControls();
    renderAnalysisOutput();
}

/**
 * Runs analysis for the current selected controls.
 *
 * @returns {Promise<void>}
 */
export async function handleRunAnalysis() {
    await runAnalysis({ scrollIntoView: true });
}

/**
 * Returns the analysis request currently represented by visible state.
 *
 * @returns {{ textColumnName: string, modelKey: string }} Active analysis request fields.
 */
export function getActiveAnalysisRequest() {
    return {
        textColumnName: state.analysisResult?.text_column_name || state.selectedAnalysisColumn || "",
        modelKey: state.analysisResult?.model_key || state.selectedAnalysisModel || "",
    };
}

/**
 * Executes an analysis request and renders the resulting workspace state.
 *
 * @param {{ scrollIntoView?: boolean, preserveCurrentOutput?: boolean, requestedColumn?: string, requestedModel?: string }} [options] Run options.
 * @returns {Promise<void>}
 */
export async function runAnalysis({
    scrollIntoView = false,
    preserveCurrentOutput = false,
    requestedColumn = "",
    requestedModel = "",
} = {}) {
    const textColumnName = requestedColumn || state.selectedAnalysisColumn || state.analysisResult?.text_column_name || "";
    const modelKey = requestedModel || state.selectedAnalysisModel || state.analysisResult?.model_key || "";
    if (!state.resultId || !textColumnName) {
        return;
    }

    const signal = beginAnalysisRun({
        textColumnName,
        modelKey,
        preserveCurrentOutput,
    });

    try {
        const response = await fetch(`/run-analysis/${encodeURIComponent(state.resultId)}`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(buildAnalysisRequestBody({ modelKey, textColumnName })),
            signal,
        });
        const payload = await handleAnalysisResponse(response);
        if (!payload) {
            return;
        }
        finishSuccessfulAnalysis({
            payload,
            textColumnName,
            modelKey,
            scrollIntoView,
        });
    } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
            return;
        }
        finishFailedAnalysis({
            error,
            textColumnName,
            modelKey,
        });
    } finally {
        activeAnalysisAbortController = null;
        state.analysisRunning = false;
        renderAnalysisControls();
    }
}

function beginAnalysisRun({ textColumnName, modelKey, preserveCurrentOutput }) {
    closeAnalysisGroupModal();
    state.selectedAnalysisColumn = textColumnName;
    state.selectedAnalysisModel = modelKey || state.selectedAnalysisModel;
    state.analysisRunning = true;
    renderAnalysisControls();
    if (preserveCurrentOutput && state.currentWorkspace === "analysis-results" && state.analysisResult) {
        renderAnalysisMessage("neutral", "Updating the plot for the current filters...");
    } else {
        state.analysisResult = null;
        renderAnalysisOutput();
    }

    if (activeAnalysisAbortController) {
        activeAnalysisAbortController.abort();
    }
    activeAnalysisAbortController = new AbortController();
    return activeAnalysisAbortController.signal;
}

function buildAnalysisRequestBody({ modelKey, textColumnName }) {
    return {
        model_key: modelKey,
        text_column_name: textColumnName,
        filters: state.activeFilters,
    };
}

async function handleAnalysisResponse(response) {
    if (response.status === 401) {
        sessionStorage.removeItem(RESULT_STORAGE_KEY);
        window.location.assign("/login");
        return null;
    }
    const payload = await parseJson(response);
    if (response.status === 404) {
        emit("workspace:missing-result", {
            message: payload.detail || "The processed result is no longer available.",
        });
        return null;
    }
    if (!response.ok) {
        throw new Error(payload.detail || "Unable to run analysis.");
    }
    return payload;
}

function finishSuccessfulAnalysis({
    payload,
    textColumnName,
    modelKey,
    scrollIntoView,
}) {
    state.analysisResult = payload;
    state.selectedAnalysisColumn = payload.text_column_name || textColumnName;
    state.selectedAnalysisModel = payload.model_key || modelKey;
    invalidateRowDatasetsAfterAnalysis();
    state.currentWorkspace = "analysis-results";
    emit("workspace:visibility:update");
    renderAnalysisOutput();
    if (scrollIntoView) {
        window.scrollTo({ top: 0, behavior: "smooth" });
    }
}

function invalidateRowDatasetsAfterAnalysis() {
    resetDatasetRows("transformed");
    resetDatasetRows("analysis");
    resetDatasetRows("community_analysis");
    state.communityAnalysisColumnNames = [];
    state.dataPreviewDataset = null;
    state.transformedHasMore = Boolean(state.resultId);
    state.analysisHasMore = Boolean(state.resultId);
    state.communityAnalysisHasMore = state.analysisResult?.model_key && state.analysisResult?.model_key !== "ngrams";
}

function finishFailedAnalysis({ error, textColumnName, modelKey }) {
    const message = error instanceof Error ? error.message : "Unable to run analysis.";
    state.analysisResult = {
        ok: false,
        result_id: state.resultId,
        model_key: modelKey,
        model_label: displayAnalysisMode(modelKey),
        text_column_name: textColumnName,
        filtered_row_count: 0,
        valid_document_count: 0,
        original_response_count: 0,
        skipped_document_count: 0,
        translated_document_count: 0,
        warnings: [],
        error: message,
        groups: [],
        ngram_buckets: [],
        scatter_points: [],
        network_edges: [],
    };
    state.currentWorkspace = "analysis-results";
    emit("workspace:visibility:update");
    renderAnalysisOutput();
}
