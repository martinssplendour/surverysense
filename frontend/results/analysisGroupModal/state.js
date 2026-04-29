// State helpers for the analysis response drilldown modal.
import {
    elements,
    prepareGroupModalState as prepareGroupModalStateTransition,
    prepareNgramModalState as prepareNgramModalStateTransition,
    resetAnalysisGroupModalState as resetAnalysisGroupModalStateTransition,
    state,
} from "../shared.js";
import { hideAnalysisGroupModalMessage } from "../filters.js";
import { normalizeValue } from "../shared/utils.js";

export function resetAnalysisGroupModalState() {
    resetAnalysisGroupModalStateTransition();
}

export function resetAndHideAnalysisGroupModal() {
    if (elements.analysisGroupModal) {
        elements.analysisGroupModal.hidden = true;
    }
    resetAnalysisGroupModalState();
    hideAnalysisGroupModalMessage();
}

export function prepareGroupModalState(group) {
    prepareGroupModalStateTransition(group);
    hideAnalysisGroupModalMessage();
}

export function prepareNgramModalState(bucket, item) {
    prepareNgramModalStateTransition(bucket, item, normalizeValue);
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
