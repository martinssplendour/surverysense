// Renders the analysis results header metadata.
import { elements, state } from "../shared.js";
import { displayColumnLabel, escapeHtml, formatNumber } from "../shared/utils.js";

export function renderAnalysisResultsHeader() {
    if (!elements.analysisResultsSubtitle) {
        return;
    }

    if (!state.analysisResult) {
        elements.analysisResultsSubtitle.textContent = "Run an analysis to see charts, distributions, and representative responses here.";
        return;
    }

    if (!state.analysisResult.ok) {
        elements.analysisResultsSubtitle.textContent = "The last analysis did not complete. Review the message below or return to the setup screen to try another method.";
        return;
    }

    const result = state.analysisResult;
    const originalResponseCount = Number(result.original_response_count || result.valid_document_count || 0);
    const questionLabel = displayColumnLabel(result.text_column_name || "");
    elements.analysisResultsSubtitle.innerHTML = `
        <span class="analysis-results-meta-item">
            <span class="analysis-results-meta-icon analysis-results-meta-icon-question" aria-hidden="true"></span>
            <span>Question:</span>
            <strong>${escapeHtml(questionLabel)}</strong>
        </span>
        <span class="analysis-results-meta-separator" aria-hidden="true"></span>
        <span class="analysis-results-meta-item">
            <span>Responses:</span>
            <strong>${formatNumber(originalResponseCount)}</strong>
        </span>
    `;
}
