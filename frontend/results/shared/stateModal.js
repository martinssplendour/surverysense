import { cloneArray, initialState, state } from "./stateCore.js";

export function resetAnalysisGroupModalState() {
    Object.assign(state.analysisGroupModal, initialState().analysisGroupModal);
}

export function prepareGroupModalState(group) {
    resetAnalysisGroupModalState();
    state.analysisGroupModal.mode = "group";
    state.analysisGroupModal.groupId = String(group.group_id || "");
    state.analysisGroupModal.totalCount = Number(group.count || 0);
}

export function prepareNgramModalState(bucket, item, normalizeValue = String) {
    resetAnalysisGroupModalState();
    state.analysisGroupModal.mode = "ngram";
    state.analysisGroupModal.ngramSize = Number(bucket.ngram_size || 0);
    state.analysisGroupModal.term = String(item.term || "");
    state.analysisGroupModal.sourceTerm = normalizeValue(item.source_term);
    state.analysisGroupModal.hitCount = Number(item.count || 0);
    state.analysisGroupModal.totalCount = Number(item.document_count || 0);
    state.analysisGroupModal.bucketLabel = String(bucket.label || `${bucket.ngram_size}-grams`);
}

export function setAnalysisGroupModalLoading(value) {
    state.analysisGroupModal.loading = Boolean(value);
}

export function setAnalysisGroupModalUnavailable(reason) {
    state.analysisGroupModal.unavailableReason = String(reason || "");
    state.analysisGroupModal.documents = [];
    state.analysisGroupModal.hasMore = false;
    state.analysisGroupModal.offset = 0;
    state.analysisGroupModal.loading = false;
}

export function applyAnalysisGroupDocumentsPayload(payload = {}, { reset = false, fallbackTotalCount = 0 } = {}) {
    const documents = cloneArray(payload.documents);
    state.analysisGroupModal.unavailableReason = "";
    state.analysisGroupModal.documents = reset
        ? documents
        : state.analysisGroupModal.documents.concat(documents);
    state.analysisGroupModal.offset = Number(payload.offset || 0) + documents.length;
    state.analysisGroupModal.hasMore = Boolean(payload.has_more);
    state.analysisGroupModal.totalCount = Number(
        payload.total_count || state.analysisGroupModal.totalCount || fallbackTotalCount || 0,
    );
    if ("hit_count" in payload) {
        state.analysisGroupModal.hitCount = Number(payload.hit_count || state.analysisGroupModal.hitCount || 0);
    }
}

export function setAnalysisDocumentTranslationLoading(documentKey, value) {
    const nextLoading = { ...state.analysisGroupModal.translationLoading };
    if (value) {
        nextLoading[documentKey] = true;
    } else {
        delete nextLoading[documentKey];
    }
    state.analysisGroupModal.translationLoading = nextLoading;
}

export function setAnalysisDocumentTranslation(documentKey, translation) {
    state.analysisGroupModal.translations = {
        ...state.analysisGroupModal.translations,
        [documentKey]: {
            text: String(translation.text || ""),
            translated: Boolean(translation.translated),
            warning: translation.warning ? String(translation.warning) : "",
        },
    };
}
