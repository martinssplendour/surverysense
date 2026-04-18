import { elements } from "./shared.js";
import { closeAnalysisGroupModal } from "./modals.js";
import { closeColumnRoleModal } from "./columnRoles.js";
import { closeFilterModal } from "./workspaceFilterBar.js";

export function handleDocumentKeydown(event) {
    if (!(event instanceof KeyboardEvent)) {
        return;
    }

    if (event.key === "Escape") {
        if (!elements.analysisGroupModal?.hidden) {
            closeAnalysisGroupModal();
            return;
        }
        if (!elements.columnRoleModal?.hidden) {
            closeColumnRoleModal();
            return;
        }
        if (!elements.filterModal?.hidden) {
            closeFilterModal();
        }
        return;
    }

    if (event.key !== "Tab") {
        return;
    }

    const activeModal = getActiveModalCard();
    if (!(activeModal instanceof HTMLElement)) {
        return;
    }

    trapFocusWithinModal(event, activeModal);
}

function getActiveModalCard() {
    if (!elements.analysisGroupModal?.hidden) {
        return elements.analysisGroupModalCard;
    }
    if (!elements.columnRoleModal?.hidden) {
        return elements.columnRoleModal?.querySelector(".modal-card");
    }
    if (!elements.filterModal?.hidden) {
        return elements.filterModal?.querySelector(".modal-card");
    }
    return null;
}

function trapFocusWithinModal(event, modalCard) {
    const focusable = Array.from(
        modalCard.querySelectorAll(
            'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
    ).filter((element) => element instanceof HTMLElement && !element.hidden && element.offsetParent !== null);

    if (!focusable.length) {
        event.preventDefault();
        modalCard.focus();
        return;
    }

    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const active = document.activeElement;

    if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus();
        return;
    }

    if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
    }
}
