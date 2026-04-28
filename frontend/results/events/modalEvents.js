import { elements, state } from "../shared.js";
import {
    closeAnalysisGroupModal,
    loadAnalysisGroupDocuments,
    loadAnalysisNgramDocuments,
    translateAnalysisDocument,
} from "../modals.js";
import {
    applyColumnRoleChange,
    closeColumnRoleModal,
    handleColumnRoleSearch,
    openColumnRoleModal,
    renderColumnRoleSelectionState,
} from "../columnRoles.js";
import { closeFilterModal, handleDocumentKeydown, openFilterModal } from "../workspace/workspace.js";

export function bindModalEvents() {
    elements.openFilterModalButton?.addEventListener("click", openFilterModal);
    elements.openAnalysisResultsFilterModalButton?.addEventListener("click", openFilterModal);
    elements.editColumnsButton?.addEventListener("click", openColumnRoleModal);
    elements.columnRoleBackdrop?.addEventListener("click", closeColumnRoleModal);
    elements.closeColumnRoleModalButton?.addEventListener("click", closeColumnRoleModal);
    elements.columnRoleSearch?.addEventListener("input", handleColumnRoleSearch);
    elements.columnRoleSelect?.addEventListener("change", renderColumnRoleSelectionState);
    elements.applyColumnRoleButton?.addEventListener("click", () => {
        void applyColumnRoleChange();
    });
    elements.filterBackdrop?.addEventListener("click", closeFilterModal);
    elements.closeFilterModalButton?.addEventListener("click", closeFilterModal);
    elements.analysisGroupBackdrop?.addEventListener("click", closeAnalysisGroupModal);
    elements.closeAnalysisGroupModalButton?.addEventListener("click", closeAnalysisGroupModal);
    elements.analysisGroupLoadAllButton?.addEventListener("click", () => {
        if (state.analysisGroupModalMode === "ngram") {
            void loadAnalysisNgramDocuments({ reset: true });
            return;
        }
        void loadAnalysisGroupDocuments({ reset: true });
    });
    elements.analysisGroupLoadMoreButton?.addEventListener("click", () => {
        if (state.analysisGroupModalMode === "ngram") {
            void loadAnalysisNgramDocuments();
            return;
        }
        void loadAnalysisGroupDocuments();
    });
    elements.analysisGroupDocuments?.addEventListener("click", handleTranslateDocumentClick);
    document.addEventListener("keydown", handleDocumentKeydown);
}

function handleTranslateDocumentClick(event) {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
        return;
    }
    const translateButton = target.closest("[data-translate-document]");
    if (!(translateButton instanceof HTMLElement)) {
        return;
    }
    const documentKey = translateButton.dataset.translateDocument;
    if (!documentKey) {
        return;
    }
    void translateAnalysisDocument(documentKey);
}
