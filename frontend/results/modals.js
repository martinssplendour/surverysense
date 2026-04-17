// Controls the drilldown modal that shows individual responses for a topic group or n-gram phrase match.
import {
    FULL_DATA_ROW_PAGE_SIZE,
    RESULT_STORAGE_KEY,
    elements,
    state,
} from "./shared.js";
import { escapeHtml, formatNumber, normalizeValue } from "./utils.js";
import { hideAnalysisGroupModalMessage, showAnalysisGroupModalMessage } from "./filters.js";
import { parseJson } from "./rows.js";

export function openAnalysisGroupModalByIndex(groupIndex) {
    const groups = Array.isArray(state.analysisResult?.groups) ? state.analysisResult.groups : [];
    const group = groups[groupIndex];
    if (!group || !elements.analysisGroupModal) {
        return;
    }

    // Reset modal-local state every time so switching between groups never leaks
    // pagination, cached translations, or stale counts from the previous drilldown.
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
    elements.analysisGroupModal.hidden = false;
    renderAnalysisGroupModal();
    void loadAnalysisNgramDocuments({ reset: true });
}

export function closeAnalysisGroupModal() {
    if (!elements.analysisGroupModal) {
        return;
    }
    elements.analysisGroupModal.hidden = true;
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
    hideAnalysisGroupModalMessage();
}

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

function getActiveAnalysisGroup() {
    const groupId = state.analysisGroupModalGroupId;
    if (state.analysisGroupModalMode !== "group" || !groupId || !Array.isArray(state.analysisResult?.groups)) {
        return null;
    }
    return state.analysisResult.groups.find((group) => String(group.group_id || "") === groupId) || null;
}

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

function renderAnalysisGroupModal() {
    syncAnalysisGroupModalAppearance();
    if (state.analysisGroupModalMode === "ngram") {
        renderAnalysisNgramModal();
        return;
    }

    const group = getActiveAnalysisGroup();
    if (!group) {
        closeAnalysisGroupModal();
        return;
    }

    const count = Number(state.analysisGroupModalTotalCount || group.count || 0);
    const loadedCount = state.analysisGroupModalDocuments.length;
    const percent = typeof group.share === "number" ? Math.round(group.share * 100) : 0;
    const modelKey = state.analysisResult?.model_key || state.selectedAnalysisModel;
    const subjectLabel = modelKey === "bertopic" ? "Topic" : "Group";
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
            { value: percent ? `${percent}% usable` : "" },
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
        if (loadedCount) {
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
        elements.analysisGroupLoadMoreButton.hidden = !state.analysisGroupModalHasMore;
        elements.analysisGroupLoadMoreButton.disabled = state.analysisGroupModalLoading;
        elements.analysisGroupLoadMoreButton.textContent = state.analysisGroupModalLoading && state.analysisGroupModalDocuments.length > 0
            ? "Loading..."
            : "Load more";
    }
}

function renderAnalysisNgramModal() {
    if (!elements.analysisGroupModal || !state.analysisGroupModalTerm) {
        closeAnalysisGroupModal();
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
        if (state.analysisGroupModalDocuments.length) {
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
        elements.analysisGroupLoadMoreButton.hidden = !state.analysisGroupModalHasMore;
        elements.analysisGroupLoadMoreButton.disabled = state.analysisGroupModalLoading;
        elements.analysisGroupLoadMoreButton.textContent = state.analysisGroupModalLoading && state.analysisGroupModalDocuments.length > 0
            ? "Loading..."
            : "Load more";
    }
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

// Composite key used to match a document in the translations and loading maps (row number + text content).
function buildDocumentKey(document) {
    return `${Number(document?.row_number || 0)}:${String(document?.text || "")}`;
}
