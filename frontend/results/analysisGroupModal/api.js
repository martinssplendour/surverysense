// Network actions for analysis response drilldown documents and translations.
import {
    FULL_DATA_ROW_PAGE_SIZE,
    RESULT_STORAGE_KEY,
    applyAnalysisGroupDocumentsPayload,
    setAnalysisDocumentTranslation,
    setAnalysisDocumentTranslationLoading,
    setAnalysisGroupModalLoading,
    setAnalysisGroupModalUnavailable,
    state,
} from "../shared.js";
import { showAnalysisGroupModalMessage, hideAnalysisGroupModalMessage } from "../filters.js";
import { parseJson } from "../data/rows.js";
import { emit } from "../events/bus.js";
import { renderAnalysisGroupModal } from "./render.js";
import { buildDocumentKey, getActiveAnalysisGroup } from "./state.js";

const MISSING_ANALYSIS_PATTERNS = [/No stored analysis snapshot exists/i];
const MISSING_RESULT_PATTERNS = [/No stored result exists/i];
const STALE_ANALYSIS_MESSAGE = "These saved response details are no longer available. Run the analysis again to refresh them.";

function isMissingAnalysisPayload(response, payload) {
    if (response.status !== 404) {
        return false;
    }
    const detail = typeof payload?.detail === "string" ? payload.detail : "";
    return MISSING_ANALYSIS_PATTERNS.some((pattern) => pattern.test(detail));
}

function isMissingResultPayload(response, payload) {
    if (response.status === 403) {
        return true;
    }
    if (response.status !== 404) {
        return false;
    }
    const detail = typeof payload?.detail === "string" ? payload.detail : "";
    return MISSING_RESULT_PATTERNS.some((pattern) => pattern.test(detail));
}

function markAnalysisDocumentsUnavailable() {
    setAnalysisGroupModalUnavailable(STALE_ANALYSIS_MESSAGE);
    showAnalysisGroupModalMessage("warning", "Analysis details need to be refreshed.");
}

export async function translateAnalysisDocument(documentKey) {
    const document = state.analysisGroupModalDocuments.find((item) => buildDocumentKey(item) === documentKey) || null;
    if (!document || !state.resultId || state.analysisGroupModalTranslationLoading[documentKey]) {
        return;
    }

    setAnalysisDocumentTranslationLoading(documentKey, true);
    renderAnalysisGroupModal();

    try {
        // Translation happens on demand per response so the main analysis path stays
        // fast and the modal only pays this cost when the user explicitly asks for it.
        const response = await fetch("/translate-to-english", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                text: String(document.text || ""),
            }),
        });
        if (response.status === 401) {
            sessionStorage.removeItem(RESULT_STORAGE_KEY);
            window.location.assign("/login");
            return;
        }
        const payload = await parseJson(response);
        if (!response.ok) {
            throw new Error(payload.detail || "Unable to translate this response.");
        }

        setAnalysisDocumentTranslation(documentKey, {
            text: String(payload.translated_text || document.text || ""),
            translated: Boolean(payload.translated),
            warning: payload.warning ? String(payload.warning) : "",
        });
    } catch (error) {
        const message = error instanceof Error ? error.message : "Unable to translate this response.";
        showAnalysisGroupModalMessage("error", message);
    } finally {
        setAnalysisDocumentTranslationLoading(documentKey, false);
        renderAnalysisGroupModal();
    }
}


export async function loadAnalysisGroupDocuments({ reset = false } = {}) {
    const group = getActiveAnalysisGroup();
    if (!group || !state.resultId || state.analysisGroupModalLoading) {
        return;
    }

    // Group documents page independently from the main analysis payload so the
    // analysis result stays lightweight even when a group has many responses.
    const offset = reset ? 0 : state.analysisGroupModalOffset;
    setAnalysisGroupModalLoading(true);
    hideAnalysisGroupModalMessage();
    renderAnalysisGroupModal();

    try {
        const query = new URLSearchParams({
            group_id: String(group.group_id || ""),
            offset: String(offset),
            limit: String(FULL_DATA_ROW_PAGE_SIZE),
        });
        const response = await fetch(`/analysis-group-documents/${encodeURIComponent(state.resultId)}?${query.toString()}`);
        if (response.status === 401) {
            sessionStorage.removeItem(RESULT_STORAGE_KEY);
            window.location.assign("/login");
            return;
        }
        const payload = await parseJson(response);
        if (isMissingResultPayload(response, payload)) {
            emit("workspace:missing-result", {
                message: payload.detail || "The processed result is no longer available.",
            });
            return;
        }
        if (isMissingAnalysisPayload(response, payload)) {
            markAnalysisDocumentsUnavailable();
            return;
        }
        if (!response.ok) {
            throw new Error(payload.detail || "Unable to load group responses.");
        }

        applyAnalysisGroupDocumentsPayload(payload, { reset, fallbackTotalCount: Number(group.count || 0) });
    } catch (error) {
        console.error(error);
        showAnalysisGroupModalMessage("error", "We couldn't load these responses. Please try again.");
    } finally {
        setAnalysisGroupModalLoading(false);
        renderAnalysisGroupModal();
    }
}


export async function loadAnalysisNgramDocuments({ reset = false } = {}) {
    if (
        state.analysisGroupModalMode !== "ngram"
        || !state.resultId
        || !state.analysisGroupModalTerm
        || !state.analysisGroupModalNgramSize
        || state.analysisGroupModalLoading
    ) {
        return;
    }

    const offset = reset ? 0 : state.analysisGroupModalOffset;
    // Use the pre-normalised source term for the API query when available; the display term may be cleaned.
    const lookupTerm = state.analysisGroupModalSourceTerm || state.analysisGroupModalTerm;
    setAnalysisGroupModalLoading(true);
    hideAnalysisGroupModalMessage();
    renderAnalysisGroupModal();

    try {
        const query = new URLSearchParams({
            ngram_size: String(state.analysisGroupModalNgramSize),
            term: lookupTerm,
            offset: String(offset),
            limit: String(FULL_DATA_ROW_PAGE_SIZE),
        });
        const response = await fetch(`/analysis-ngram-documents/${encodeURIComponent(state.resultId)}?${query.toString()}`);
        if (response.status === 401) {
            sessionStorage.removeItem(RESULT_STORAGE_KEY);
            window.location.assign("/login");
            return;
        }
        const payload = await parseJson(response);
        if (isMissingResultPayload(response, payload)) {
            emit("workspace:missing-result", {
                message: payload.detail || "The processed result is no longer available.",
            });
            return;
        }
        if (isMissingAnalysisPayload(response, payload)) {
            markAnalysisDocumentsUnavailable();
            return;
        }
        if (!response.ok) {
            throw new Error(payload.detail || "Unable to load matching responses.");
        }

        applyAnalysisGroupDocumentsPayload(payload, { reset });
    } catch (error) {
        console.error(error);
        showAnalysisGroupModalMessage("error", "We couldn't load these matching responses. Please try again.");
    } finally {
        setAnalysisGroupModalLoading(false);
        renderAnalysisGroupModal();
    }
}
