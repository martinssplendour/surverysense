// Opens and closes the analysis response drilldown modal.
import { elements, state } from "../shared.js";
import { loadAnalysisGroupDocuments, loadAnalysisNgramDocuments } from "./api.js";
import { renderAnalysisGroupModal } from "./render.js";
import {
    prepareGroupModalState,
    prepareNgramModalState,
    resetAndHideAnalysisGroupModal,
} from "./state.js";

export function openAnalysisGroupModalByIndex(groupIndex) {
    const groups = Array.isArray(state.analysisResult?.groups) ? state.analysisResult.groups : [];
    const group = groups[groupIndex];
    if (!group || !elements.analysisGroupModal) {
        return;
    }

    // Reset modal-local state every time so switching between groups never leaks
    // pagination, cached translations, or stale counts from the previous drilldown.
    prepareGroupModalState(group);
    elements.analysisGroupModal.hidden = false;
    renderAnalysisGroupModal();
    void loadAnalysisGroupDocuments({ reset: true });
}

export function openAnalysisNgramModal(bucketIndex, itemIndex) {
    const buckets = Array.isArray(state.analysisResult?.ngram_buckets) ? state.analysisResult.ngram_buckets : [];
    const bucket = buckets[bucketIndex];
    const items = Array.isArray(bucket?.items) ? bucket.items : [];
    const item = items[itemIndex];
    if (!bucket || !item || !elements.analysisGroupModal) {
        return;
    }

    prepareNgramModalState(bucket, item);
    elements.analysisGroupModal.hidden = false;
    renderAnalysisGroupModal();
    void loadAnalysisNgramDocuments({ reset: true });
}

export function closeAnalysisGroupModal() {
    resetAndHideAnalysisGroupModal();
}
