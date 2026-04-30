// Renders the analysis response drilldown modal for topic groups and n-gram matches.
import { elements, state } from "../shared.js";
import { escapeHtml, formatNumber } from "../shared/utils.js";
import {
    buildDocumentKey,
    getActiveAnalysisGroup,
    resetAndHideAnalysisGroupModal,
} from "./state.js";

function syncAnalysisGroupModalAppearance() {
    if (!(elements.analysisGroupModalCard instanceof HTMLElement)) {
        return;
    }
    elements.analysisGroupModalCard.classList.toggle(
        "analysis-group-modal-card-ngram",
        state.analysisGroupModalMode === "ngram" || state.analysisGroupModalMode === "group",
    );
}


function renderAnalysisModalStatPills(items) {
    return items
        .filter((item) => item && item.value)
        .map((item) => `
            <span class="analysis-group-stat-pill">
                <span class="analysis-group-stat-icon" aria-hidden="true"></span>
                <span>${escapeHtml(item.value)}</span>
            </span>
        `)
        .join("");
}


function renderAnalysisModalContext(items) {
    return items
        .filter(Boolean)
        .map((item) => `<span>${escapeHtml(String(item))}</span>`)
        .join("");
}


export function renderAnalysisGroupModal() {
    syncAnalysisGroupModalAppearance();
    if (state.analysisGroupModalMode === "ngram") {
        renderAnalysisNgramModal();
        return;
    }

    const group = getActiveAnalysisGroup();
    if (!group) {
        resetAndHideAnalysisGroupModal();
        return;
    }

    const count = Number(state.analysisGroupModalTotalCount || group.count || 0);
    const loadedCount = state.analysisGroupModalDocuments.length;
    const modelKey = state.analysisResult?.model_key || state.selectedAnalysisModel;
    const subjectLabel = modelKey === "community"
        ? "Community"
        : "Group";
    const contextItems = [
        group.translated && !group.ai_generated ? "Translated label" : "",
        Array.isArray(group.terms) && group.terms.length
            ? `Top terms: ${group.terms.slice(0, 4).join(", ")}`
            : "",
        group.is_noise ? "Outlier bucket" : "",
    ];
    // The same modal shell renders both group drilldowns and n-gram matches; the
    // header/context block is rebuilt from whichever analysis mode is active.
    const detailsMarkup = renderAnalysisModalContext(contextItems);

    if (elements.analysisGroupTitle) {
        elements.analysisGroupTitle.textContent = group.label || "Unlabelled group";
    }
    if (elements.analysisGroupKicker) {
        elements.analysisGroupKicker.textContent = `${subjectLabel} Responses`;
    }
    if (elements.analysisGroupMeta) {
        elements.analysisGroupMeta.innerHTML = renderAnalysisModalStatPills([
            { value: `${formatNumber(count)} responses` },
        ]);
    }
    if (elements.analysisGroupTerms) {
        elements.analysisGroupTerms.hidden = !detailsMarkup;
        elements.analysisGroupTerms.innerHTML = detailsMarkup;
    }
    if (elements.analysisGroupExamplesSection) {
        elements.analysisGroupExamplesSection.hidden = true;
    }
    if (elements.analysisGroupExamplesTitle) {
        elements.analysisGroupExamplesTitle.textContent = "";
    }
    if (elements.analysisGroupExamplesSubtitle) {
        elements.analysisGroupExamplesSubtitle.textContent = "";
    }
    if (elements.analysisGroupExamples) {
        elements.analysisGroupExamples.innerHTML = "";
    }
    if (elements.analysisGroupLoadAllButton) {
        elements.analysisGroupLoadAllButton.hidden = true;
    }
    if (elements.analysisGroupFullSection) {
        elements.analysisGroupFullSection.hidden = false;
    }
    if (elements.analysisGroupFullTitle) {
        elements.analysisGroupFullTitle.textContent = loadedCount
            ? `${subjectLabel} Responses (${formatNumber(loadedCount)} of ${formatNumber(count)})`
            : `${subjectLabel} Responses`;
    }
    if (elements.analysisGroupDocuments) {
        if (state.analysisGroupModalUnavailableReason) {
            elements.analysisGroupDocuments.innerHTML = renderAnalysisRecoveryPanel(state.analysisGroupModalUnavailableReason);
        } else if (loadedCount) {
            elements.analysisGroupDocuments.innerHTML = state.analysisGroupModalDocuments
                .map((document) => renderAnalysisDocumentCard(document))
                .join("");
        } else if (state.analysisGroupModalLoading) {
            elements.analysisGroupDocuments.innerHTML = `<p class="analysis-sample">Loading ${subjectLabel.toLowerCase()} responses...</p>`;
        } else {
            elements.analysisGroupDocuments.innerHTML = `<p class="analysis-sample">No responses were found for this ${subjectLabel.toLowerCase()}.</p>`;
        }
    }
    if (elements.analysisGroupLoadMoreButton) {
        elements.analysisGroupLoadMoreButton.hidden = Boolean(state.analysisGroupModalUnavailableReason)
            || !state.analysisGroupModalHasMore;
        elements.analysisGroupLoadMoreButton.disabled = state.analysisGroupModalLoading;
        elements.analysisGroupLoadMoreButton.textContent = state.analysisGroupModalLoading && state.analysisGroupModalDocuments.length > 0
            ? "Loading..."
            : "Load more";
    }
}


function renderAnalysisNgramModal() {
    if (!elements.analysisGroupModal || !state.analysisGroupModalTerm) {
        resetAndHideAnalysisGroupModal();
        return;
    }

    if (elements.analysisGroupKicker) {
        elements.analysisGroupKicker.textContent = "Phrase Matches";
    }
    if (elements.analysisGroupTitle) {
        elements.analysisGroupTitle.textContent = state.analysisGroupModalTerm;
    }
    if (elements.analysisGroupMeta) {
        const totalCount = Number(state.analysisGroupModalTotalCount || 0);
        const hitCount = Number(state.analysisGroupModalHitCount || 0);
        elements.analysisGroupMeta.innerHTML = renderAnalysisModalStatPills([
            { value: `${formatNumber(totalCount)} matching response${totalCount === 1 ? "" : "s"}` },
            { value: `${formatNumber(hitCount)} total hit${hitCount === 1 ? "" : "s"}` },
        ]);
    }
    if (elements.analysisGroupTerms) {
        const detailsMarkup = renderAnalysisModalContext([
            state.analysisGroupModalBucketLabel,
            state.analysisGroupModalSourceTerm ? `Original phrase: ${state.analysisGroupModalSourceTerm}` : "",
        ]);
        elements.analysisGroupTerms.hidden = !detailsMarkup;
        elements.analysisGroupTerms.innerHTML = detailsMarkup;
    }
    if (elements.analysisGroupExamplesSection) {
        elements.analysisGroupExamplesSection.hidden = true;
    }
    if (elements.analysisGroupExamplesSubtitle) {
        elements.analysisGroupExamplesSubtitle.textContent = "";
    }
    if (elements.analysisGroupExamples) {
        elements.analysisGroupExamples.innerHTML = "";
    }
    if (elements.analysisGroupLoadAllButton) {
        elements.analysisGroupLoadAllButton.hidden = true;
    }
    if (elements.analysisGroupFullSection) {
        elements.analysisGroupFullSection.hidden = false;
    }
    if (elements.analysisGroupFullTitle) {
        const totalCount = Number(state.analysisGroupModalTotalCount || 0);
        elements.analysisGroupFullTitle.textContent = totalCount
            ? `Matching Responses (${formatNumber(state.analysisGroupModalDocuments.length)} of ${formatNumber(totalCount)})`
            : "Matching Responses";
    }
    if (elements.analysisGroupDocuments) {
        if (state.analysisGroupModalUnavailableReason) {
            elements.analysisGroupDocuments.innerHTML = renderAnalysisRecoveryPanel(state.analysisGroupModalUnavailableReason);
        } else if (state.analysisGroupModalDocuments.length) {
            elements.analysisGroupDocuments.innerHTML = state.analysisGroupModalDocuments
                .map((document) => renderAnalysisDocumentCard(document))
                .join("");
        } else if (state.analysisGroupModalLoading) {
            elements.analysisGroupDocuments.innerHTML = '<p class="analysis-sample">Loading matching responses...</p>';
        } else {
            elements.analysisGroupDocuments.innerHTML = '<p class="analysis-sample">No matching responses were found for this phrase.</p>';
        }
    }
    if (elements.analysisGroupLoadMoreButton) {
        elements.analysisGroupLoadMoreButton.hidden = Boolean(state.analysisGroupModalUnavailableReason)
            || !state.analysisGroupModalHasMore;
        elements.analysisGroupLoadMoreButton.disabled = state.analysisGroupModalLoading;
        elements.analysisGroupLoadMoreButton.textContent = state.analysisGroupModalLoading && state.analysisGroupModalDocuments.length > 0
            ? "Loading..."
            : "Load more";
    }
}


function renderAnalysisRecoveryPanel(message) {
    return `
        <div class="analysis-modal-recovery" role="status">
            <div>
                <h5>Response details need to be refreshed</h5>
                <p>${escapeHtml(message)}</p>
            </div>
            <button type="button" class="button button-primary" data-rerun-analysis>
                Run analysis again
            </button>
        </div>
    `;
}


function renderAnalysisDocumentCard(document) {
    const documentKey = buildDocumentKey(document);
    const translation = state.analysisGroupModalTranslations[documentKey] || null;
    const isLoading = Boolean(state.analysisGroupModalTranslationLoading[documentKey]);
    return `
        <blockquote class="analysis-example analysis-example-full">
            <div class="analysis-example-header">
                <span class="analysis-example-pill">Row ${Number(document.row_number || 0)}</span>
                <button
                    type="button"
                    class="button button-ghost analysis-translate-button"
                    data-translate-document="${escapeHtml(documentKey)}"
                    ${isLoading ? "disabled" : ""}
                >
                    ${isLoading ? "..." : "Translate"}
                </button>
            </div>
            <p>${escapeHtml(document.text || "")}</p>
            ${translation ? `
                <div class="analysis-example-translation">
                    <strong>English</strong>
                    <p>${escapeHtml(translation.text || "")}</p>
                    ${translation.warning ? `<span class="analysis-source-note">${escapeHtml(translation.warning)}</span>` : ""}
                </div>
            ` : ""}
        </blockquote>
    `;
}
