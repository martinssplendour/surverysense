// State helpers for the analysis response drilldown modal.
import { elements, state } from "../shared.js";
import { hideAnalysisGroupModalMessage } from "../filters.js";
import { normalizeValue } from "../shared/utils.js";

export function resetAnalysisGroupModalState() {
    state.analysisGroupModalMode = "group";
    state.analysisGroupModalGroupId = "";
    state.analysisGroupModalNgramSize = 0;
    state.analysisGroupModalTerm = "";
    state.analysisGroupModalSourceTerm = "";
    state.analysisGroupModalHitCount = 0;
    state.analysisGroupModalTotalCount = 0;
    state.analysisGroupModalBucketLabel = "";
    state.analysisGroupModalDocuments = [];
    state.analysisGroupModalTranslations = {};
    state.analysisGroupModalTranslationLoading = {};
    state.analysisGroupModalHasMore = false;
    state.analysisGroupModalOffset = 0;
    state.analysisGroupModalLoading = false;
}

export function resetAndHideAnalysisGroupModal() {
    if (elements.analysisGroupModal) {
        elements.analysisGroupModal.hidden = true;
    }
    resetAnalysisGroupModalState();
    hideAnalysisGroupModalMessage();
}

export function prepareGroupModalState(group) {
    state.analysisGroupModalMode = "group";
    state.analysisGroupModalGroupId = String(group.group_id || "");
    state.analysisGroupModalNgramSize = 0;
    state.analysisGroupModalTerm = "";
    state.analysisGroupModalSourceTerm = "";
    state.analysisGroupModalHitCount = 0;
    state.analysisGroupModalTotalCount = Number(group.count || 0);
    state.analysisGroupModalBucketLabel = "";
    state.analysisGroupModalDocuments = [];
    state.analysisGroupModalTranslations = {};
    state.analysisGroupModalTranslationLoading = {};
    state.analysisGroupModalHasMore = false;
    state.analysisGroupModalOffset = 0;
    state.analysisGroupModalLoading = false;
    hideAnalysisGroupModalMessage();
}

export function prepareNgramModalState(bucket, item) {
    state.analysisGroupModalMode = "ngram";
    state.analysisGroupModalGroupId = "";
    state.analysisGroupModalNgramSize = Number(bucket.ngram_size || 0);
    state.analysisGroupModalTerm = String(item.term || "");
    state.analysisGroupModalSourceTerm = normalizeValue(item.source_term);
    state.analysisGroupModalHitCount = Number(item.count || 0);
    state.analysisGroupModalTotalCount = Number(item.document_count || 0);
    state.analysisGroupModalBucketLabel = String(bucket.label || `${bucket.ngram_size}-grams`);
    state.analysisGroupModalDocuments = [];
    state.analysisGroupModalTranslations = {};
    state.analysisGroupModalTranslationLoading = {};
    state.analysisGroupModalHasMore = false;
    state.analysisGroupModalOffset = 0;
    state.analysisGroupModalLoading = false;
    hideAnalysisGroupModalMessage();
}

export function getActiveAnalysisGroup() {
    const groupId = state.analysisGroupModalGroupId;
    if (state.analysisGroupModalMode !== "group" || !groupId || !Array.isArray(state.analysisResult?.groups)) {
        return null;
    }
    return state.analysisResult.groups.find((group) => String(group.group_id || "") === groupId) || null;
}


// Composite key used to match a document in the translations and loading maps (row number + text content).
export function buildDocumentKey(document) {
    return `${Number(document?.row_number || 0)}:${String(document?.text || "")}`;
}
