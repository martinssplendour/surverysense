// Network actions for analysis response drilldown documents and translations.
import {
    FULL_DATA_ROW_PAGE_SIZE,
    RESULT_STORAGE_KEY,
    state,
} from "../shared.js";
import { showAnalysisGroupModalMessage, hideAnalysisGroupModalMessage } from "../filters.js";
import { parseJson } from "../data/rows.js";
import { renderAnalysisGroupModal } from "./render.js";
import { buildDocumentKey, getActiveAnalysisGroup } from "./state.js";

export async function translateAnalysisDocument(documentKey) {
    const document = state.analysisGroupModalDocuments.find((item) => buildDocumentKey(item) === documentKey) || null;
    if (!document || !state.resultId || state.analysisGroupModalTranslationLoading[documentKey]) {
        return;
    }

    state.analysisGroupModalTranslationLoading = {
        ...state.analysisGroupModalTranslationLoading,
        [documentKey]: true,
    };
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

        state.analysisGroupModalTranslations = {
            ...state.analysisGroupModalTranslations,
            [documentKey]: {
                text: String(payload.translated_text || document.text || ""),
                translated: Boolean(payload.translated),
                warning: payload.warning ? String(payload.warning) : "",
            },
        };
    } catch (error) {
        const message = error instanceof Error ? error.message : "Unable to translate this response.";
        showAnalysisGroupModalMessage("error", message);
    } finally {
        const nextLoading = { ...state.analysisGroupModalTranslationLoading };
        delete nextLoading[documentKey];
        state.analysisGroupModalTranslationLoading = nextLoading;
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
    state.analysisGroupModalLoading = true;
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
        if (!response.ok) {
            throw new Error(payload.detail || "Unable to load group responses.");
        }

        const documents = Array.isArray(payload.documents) ? payload.documents : [];
        state.analysisGroupModalDocuments = reset
            ? documents
            : state.analysisGroupModalDocuments.concat(documents);
        state.analysisGroupModalOffset = Number(payload.offset || 0) + documents.length;
        state.analysisGroupModalHasMore = Boolean(payload.has_more);
        state.analysisGroupModalTotalCount = Number(payload.total_count || state.analysisGroupModalTotalCount || group.count || 0);
    } catch (error) {
        const message = error instanceof Error ? error.message : "Unable to load group responses.";
        showAnalysisGroupModalMessage("error", message);
    } finally {
        state.analysisGroupModalLoading = false;
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
    state.analysisGroupModalLoading = true;
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
        if (!response.ok) {
            throw new Error(payload.detail || "Unable to load matching responses.");
        }

        const documents = Array.isArray(payload.documents) ? payload.documents : [];
        state.analysisGroupModalDocuments = reset
            ? documents
            : state.analysisGroupModalDocuments.concat(documents);
        state.analysisGroupModalOffset = Number(payload.offset || 0) + documents.length;
        state.analysisGroupModalHasMore = Boolean(payload.has_more);
        state.analysisGroupModalTotalCount = Number(payload.total_count || state.analysisGroupModalTotalCount || 0);
        state.analysisGroupModalHitCount = Number(payload.hit_count || state.analysisGroupModalHitCount || 0);
    } catch (error) {
        const message = error instanceof Error ? error.message : "Unable to load matching responses.";
        showAnalysisGroupModalMessage("error", message);
    } finally {
        state.analysisGroupModalLoading = false;
        renderAnalysisGroupModal();
    }
}
