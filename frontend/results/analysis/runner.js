import {
    RESULT_STORAGE_KEY,
    COMMUNITY_SIMILARITY_THRESHOLD_DEFAULT,
    invalidateRowDatasetsAfterAnalysis,
    setAnalysisResult,
    setAnalysisRunning,
    setAnalysisSelection,
    setCommunitySimilarityThreshold,
    setCurrentWorkspace,
    state,
} from "../shared.js";
import { displayAnalysisMode } from "../shared/utils.js";
import { parseJson } from "../data/rows.js";
import { emit } from "../events/bus.js";
import { closeAnalysisGroupModal } from "../modals.js";
import {
    renderAnalysisControls,
    renderAnalysisMessage,
    renderAnalysisOutput,
    renderAnalysisRetryMessage,
} from "./render.js";

let activeAnalysisAbortController = null;

const GEMINI_RATE_LIMIT_ERROR_CODE = "gemini_rate_limited";
const GEMINI_RATE_LIMIT_MAX_RETRIES = 5;
const GEMINI_RATE_LIMIT_RETRY_SECONDS = 60;
const GEMINI_RATE_LIMIT_RETRY_MESSAGE = "Due to Gemini rate limit, we are retrying in 1 minute.";
const GEMINI_RATE_LIMIT_FINAL_MESSAGE = "Gemini is still rate limited. Try again later.";

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
    setAnalysisSelection({ column: target.value, model: state.selectedAnalysisModel });
    setAnalysisResult(null);
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
    setAnalysisSelection({ column: state.selectedAnalysisColumn, model: modelKey });
    setAnalysisResult(null);
    renderAnalysisControls();
    renderAnalysisOutput();
}

/**
 * Updates the selected cosine similarity threshold for community detection.
 *
 * @param {Event} event Range input event.
 * @returns {void}
 */
export function handleCommunitySimilarityChange(event) {
    const target = event.target;
    if (!target || !("value" in target)) {
        return;
    }
    setCommunitySimilarityThreshold(target.value);
    setAnalysisResult(null);
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
        const payload = await runAnalysisWithGeminiRateLimitRetries({
            signal,
            modelKey,
            textColumnName,
        });
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
        setAnalysisRunning(false);
        renderAnalysisControls();
    }
}

function beginAnalysisRun({ textColumnName, modelKey, preserveCurrentOutput }) {
    closeAnalysisGroupModal();
    setAnalysisSelection({
        column: textColumnName,
        model: modelKey || state.selectedAnalysisModel,
    });
    setAnalysisRunning(true);
    renderAnalysisControls();
    if (preserveCurrentOutput && state.currentWorkspace === "analysis-results" && state.analysisResult) {
        renderAnalysisMessage("neutral", "Updating the plot for the current filters...");
    } else {
        setAnalysisResult(null);
        renderAnalysisOutput();
    }

    if (activeAnalysisAbortController) {
        activeAnalysisAbortController.abort();
    }
    activeAnalysisAbortController = new AbortController();
    return activeAnalysisAbortController.signal;
}

function buildAnalysisRequestBody({ modelKey, textColumnName }) {
    const body = {
        model_key: modelKey,
        text_column_name: textColumnName,
        filters: state.activeFilters,
    };
    if (modelKey === "community") {
        body.community_similarity_threshold = Number(
            state.communitySimilarityThreshold || COMMUNITY_SIMILARITY_THRESHOLD_DEFAULT,
        );
    }
    return body;
}

async function runAnalysisWithGeminiRateLimitRetries({ signal, modelKey, textColumnName }) {
    let geminiRateLimitRetries = 0;
    while (true) {
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
            return null;
        }

        if (!isGeminiRateLimitPayload(payload)) {
            return payload;
        }

        if (geminiRateLimitRetries >= GEMINI_RATE_LIMIT_MAX_RETRIES) {
            return {
                ...payload,
                error: GEMINI_RATE_LIMIT_FINAL_MESSAGE,
                retry_after_seconds: null,
            };
        }

        geminiRateLimitRetries += 1;
        renderAnalysisRetryMessage(GEMINI_RATE_LIMIT_RETRY_MESSAGE);
        const shouldContinue = await waitForRetryDelay(getRetryDelaySeconds(payload), signal);
        if (!shouldContinue) {
            return null;
        }
    }
}

function isGeminiRateLimitPayload(payload) {
    return payload?.ok === false && payload.error_code === GEMINI_RATE_LIMIT_ERROR_CODE;
}

function getRetryDelaySeconds(payload) {
    const retryAfterSeconds = Number(payload.retry_after_seconds);
    return Number.isFinite(retryAfterSeconds) && retryAfterSeconds > 0
        ? retryAfterSeconds
        : GEMINI_RATE_LIMIT_RETRY_SECONDS;
}

function waitForRetryDelay(seconds, signal) {
    if (signal.aborted) {
        return Promise.resolve(false);
    }

    return new Promise((resolve) => {
        const timeoutId = setTimeout(() => {
            cleanup();
            resolve(true);
        }, seconds * 1000);

        const abortHandler = () => {
            clearTimeout(timeoutId);
            cleanup();
            resolve(false);
        };

        function cleanup() {
            signal.removeEventListener("abort", abortHandler);
        }

        signal.addEventListener("abort", abortHandler, { once: true });
    });
}

async function handleAnalysisResponse(response) {
    if (response.status === 401) {
        sessionStorage.removeItem(RESULT_STORAGE_KEY);
        window.location.assign("/login");
        return null;
    }
    const payload = await parseJson(response);
    if (response.status === 403 || response.status === 404) {
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
    setAnalysisResult(payload);
    if (typeof payload.community_similarity_threshold === "number") {
        setCommunitySimilarityThreshold(payload.community_similarity_threshold);
    }
    setAnalysisSelection({
        column: payload.text_column_name || textColumnName,
        model: payload.model_key || modelKey,
    });
    invalidateRowDatasetsAfterAnalysis();
    setCurrentWorkspace("analysis-results");
    emit("workspace:visibility:update");
    renderAnalysisOutput();
    if (scrollIntoView) {
        window.scrollTo({ top: 0, behavior: "smooth" });
    }
}

function finishFailedAnalysis({ error, textColumnName, modelKey }) {
    const message = error instanceof Error ? error.message : "Unable to run analysis.";
    setAnalysisResult({
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
    });
    setCurrentWorkspace("analysis-results");
    emit("workspace:visibility:update");
    renderAnalysisOutput();
}
