import { ANALYSIS_MODE_OPTIONS, elements, state } from "../shared.js";
import {
    buildPercentLabel,
    displayAnalysisMode,
    displayColumnLabel,
    escapeHtml,
    formatNumber,
    normalizeValue,
} from "../shared/utils.js";
import {
    clearAnalysisChart,
    renderAnalysisChart,
    renderNgramCharts,
} from "../charts.js";
import { displayAnalysisExportFormat, normalizeAnalysisExportFormat } from "../charts/export.js";
import { callbacks } from "../analysisCallbacks.js";

export function renderAnalysisPanel() {
    const hasVerbatimColumns = state.analysisVerbatimColumns.length > 0;
    elements.analysisPanel.hidden = !hasVerbatimColumns;
    if (!hasVerbatimColumns) {
        return;
    }

    if (!state.selectedAnalysisColumn || !state.analysisVerbatimColumns.includes(state.selectedAnalysisColumn)) {
        state.selectedAnalysisColumn = state.analysisVerbatimColumns[0] || "";
    }
    if (!ANALYSIS_MODE_OPTIONS.some((option) => option.key === state.selectedAnalysisModel)) {
        state.selectedAnalysisModel = "community";
    }

    renderAnalysisControls();
}

export function renderAnalysisControls() {
    elements.analysisColumnSelect.innerHTML = state.analysisVerbatimColumns
        .map((column) => {
            const isSelected = column === state.selectedAnalysisColumn ? " selected" : "";
            return `<option value="${escapeHtml(column)}"${isSelected}>${escapeHtml(displayColumnLabel(column))}</option>`;
        })
        .join("");
    elements.analysisMethods.innerHTML = ANALYSIS_MODE_OPTIONS
        .map((option) => {
            const isSelected = option.key === state.selectedAnalysisModel;
            const iconClass = option.key === "ngrams" ? "analysis-method-icon-ngrams" : "analysis-method-icon-community";
            return `
                <button
                    type="button"
                    class="analysis-method${isSelected ? " analysis-method-active" : ""}"
                    data-model-key="${escapeHtml(option.key)}"
                    aria-pressed="${isSelected ? "true" : "false"}"
                >
                    <span class="analysis-method-radio" aria-hidden="true"></span>
                    <span class="analysis-method-icon ${iconClass}" aria-hidden="true"></span>
                    <span class="analysis-method-copy-block">
                        <span class="analysis-method-title">${escapeHtml(option.label)}</span>
                        <span class="analysis-method-copy">${escapeHtml(option.description)}</span>
                    </span>
                </button>
            `;
        })
        .join("");
    elements.runAnalysisButton.disabled = state.analysisRunning || !state.selectedAnalysisColumn;
    elements.runAnalysisButton.innerHTML = state.analysisRunning
        ? '<span class="analysis-run-button-content"><span class="analysis-run-spinner" aria-hidden="true"></span><span>Running Analysis...</span></span>'
        : '<span class="analysis-run-button-content"><span class="analysis-run-icon" aria-hidden="true"></span><span>Run Analysis</span></span>';
}

export function renderAnalysisOutput() {
    renderAnalysisResultsHeader();
    callbacks.renderFilterBar();
    renderAnalysisExportControls();

    if (!state.analysisResult) {
        elements.analysisSummary.innerHTML = "";
        elements.analysisSummary.hidden = true;
        clearAnalysisChart();
        elements.analysisList.innerHTML = "";
        elements.analysisNgramGrid.innerHTML = "";
        clearAnalysisMessage();
        setAnalysisEmptyState(true);
        return;
    }

    const result = state.analysisResult;
    if (!result.ok) {
        setAnalysisEmptyState(false);
        elements.analysisSummary.innerHTML = "";
        elements.analysisSummary.hidden = true;
        clearAnalysisChart();
        elements.analysisList.innerHTML = `
            <div class="analysis-item">
                <h4>Analysis could not run</h4>
                <p class="analysis-sample">${escapeHtml(result.error || "The selected analysis failed.")}</p>
            </div>
        `;
        elements.analysisNgramGrid.innerHTML = "";
        renderAnalysisMessage("error", result.error || "The selected analysis failed.");
        return;
    }

    setAnalysisEmptyState(false);
    renderAnalysisInsightSummary(result);
    clearAnalysisMessage();

    if (Array.isArray(result.ngram_buckets) && result.ngram_buckets.length) {
        elements.analysisList.innerHTML = "";
        elements.analysisNgramGrid.innerHTML = "";
        renderNgramCharts(result.ngram_buckets);
        return;
    }

    const groups = Array.isArray(result.groups) ? result.groups : [];
    elements.analysisNgramGrid.innerHTML = "";
    elements.analysisList.innerHTML = groups.length
        ? ""
        : `
            <div class="analysis-item">
                <h4>No groups were returned</h4>
                <p class="analysis-sample">The analysis completed, but it did not produce any usable topics or groups for the current filtered sample.</p>
            </div>
        `;
    renderAnalysisChart(
        groups,
        Array.isArray(result.scatter_points) ? result.scatter_points : [],
        Array.isArray(result.network_edges) ? result.network_edges : [],
    );
}

export function renderAnalysisExportControls() {
    const hasReadyAnalysis = Boolean(state.resultId && state.analysisResult && state.analysisResult.ok);
    const selectedFormat = normalizeAnalysisExportFormat(state.analysisExportFormat);
    const selectedFormatLabel = displayAnalysisExportFormat(selectedFormat);
    if (!hasReadyAnalysis || state.analysisExportRunning) {
        state.analysisExportMenuOpen = false;
    }
    const isMenuOpen = hasReadyAnalysis && !state.analysisExportRunning && Boolean(state.analysisExportMenuOpen);
    if (elements.previewAnalysisReportButton) {
        elements.previewAnalysisReportButton.disabled = !hasReadyAnalysis || state.analysisExportRunning;
        elements.previewAnalysisReportButton.textContent = "Preview";
        elements.previewAnalysisReportButton.title = hasReadyAnalysis
            ? `Open a preview page for the generated ${selectedFormatLabel} report`
            : "Run an analysis to enable report preview";
    }
    if (elements.downloadAnalysisReportButton) {
        elements.downloadAnalysisReportButton.disabled = !hasReadyAnalysis || state.analysisExportRunning;
        elements.downloadAnalysisReportButton.textContent = state.analysisExportRunning
            ? "Preparing..."
            : `Download ${selectedFormatLabel}`;
        elements.downloadAnalysisReportButton.title = hasReadyAnalysis
            ? `Download report as ${selectedFormatLabel}`
            : "Run an analysis to enable report download";
    }
    if (elements.analysisExportToggleButton) {
        elements.analysisExportToggleButton.disabled = !hasReadyAnalysis || state.analysisExportRunning;
        elements.analysisExportToggleButton.setAttribute("aria-expanded", isMenuOpen ? "true" : "false");
        elements.analysisExportToggleButton.title = hasReadyAnalysis
            ? `Choose report format. Current format: ${selectedFormatLabel}`
            : "Run an analysis to choose a report format";
    }
    if (elements.analysisExportMenu) {
        elements.analysisExportMenu.hidden = !isMenuOpen;
        const items = elements.analysisExportMenu.querySelectorAll("[data-export-format]");
        items.forEach((item) => {
            if (!(item instanceof HTMLElement)) {
                return;
            }
            const itemFormat = normalizeAnalysisExportFormat(item.dataset.exportFormat);
            const isSelected = itemFormat === selectedFormat;
            item.classList.toggle("analysis-export-menu-item-selected", isSelected);
            item.setAttribute("aria-checked", isSelected ? "true" : "false");
            item.tabIndex = isMenuOpen ? 0 : -1;
        });
    }
}

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
    const methodLabel = displayAnalysisMethodLabel(result.model_key || state.selectedAnalysisModel);
    elements.analysisResultsSubtitle.textContent = `${questionLabel} | ${formatNumber(originalResponseCount)} responses`;
    elements.analysisResultsSubtitle.innerHTML = `
        <span class="analysis-results-meta-item">
            <span class="analysis-results-meta-icon analysis-results-meta-icon-question" aria-hidden="true"></span>
            <span>Question:</span>
            <strong>${escapeHtml(questionLabel)}</strong>
        </span>
        <span class="analysis-results-meta-separator" aria-hidden="true"></span>
        <span class="analysis-results-meta-item">
            <span class="analysis-results-meta-icon analysis-results-meta-icon-method" aria-hidden="true"></span>
            <span>Method:</span>
            <strong>${escapeHtml(methodLabel)}</strong>
        </span>
        <span class="analysis-results-meta-separator" aria-hidden="true"></span>
        <span class="analysis-results-meta-item">
            <span>Responses:</span>
            <strong>${formatNumber(originalResponseCount)}</strong>
        </span>
    `;
}

export function renderAnalysisMessage(kind, message) {
    elements.analysisMessage.hidden = false;
    elements.analysisMessage.className = `analysis-message analysis-message-${kind}`;
    elements.analysisMessage.textContent = message;
}

export function clearAnalysisMessage() {
    if (!elements.analysisMessage) {
        return;
    }
    elements.analysisMessage.hidden = true;
    elements.analysisMessage.textContent = "";
    elements.analysisMessage.className = "analysis-message";
}

function setAnalysisEmptyState(show) {
    if (elements.analysisEmptyState) {
        elements.analysisEmptyState.hidden = !show;
    }
}

function renderAnalysisInsightSummary(result) {
    if (!elements.analysisSummary) {
        return;
    }

    const groups = Array.isArray(result.groups)
        ? [...result.groups].sort((left, right) => Number(right.count || 0) - Number(left.count || 0))
        : [];
    if (groups.length) {
        elements.analysisSummary.hidden = false;
        elements.analysisSummary.innerHTML = buildTopGroupInsight(groups[0]);
        return;
    }

    const topNgramItem = findTopNgramItem(result);
    if (topNgramItem) {
        elements.analysisSummary.hidden = false;
        elements.analysisSummary.innerHTML = buildTopNgramInsight(topNgramItem);
        return;
    }

    elements.analysisSummary.innerHTML = "";
    elements.analysisSummary.hidden = true;
}

function buildTopGroupInsight(group) {
    const label = normalizeValue(group.label) || "Top Theme";
    const count = Number(group.count || 0);
    const percent = buildPercentLabel(group.share);
    const percentText = percent === "Not available" ? "" : ` (${percent})`;
    const insightCopy = percent === "Not available"
        ? `${formatNumber(count)} response(s) mention this theme.`
        : `${percent} of responses mention this theme.`;

    return `
        <article class="analysis-insight-card">
            <div class="analysis-insight-icon" aria-hidden="true">
                <span></span>
            </div>
            <div class="analysis-insight-copy">
                <p class="analysis-insight-kicker">Top Insight</p>
                <h3>${escapeHtml(label)} is the most common theme.</h3>
                <p>${escapeHtml(insightCopy)}</p>
            </div>
            <div class="analysis-insight-divider" aria-hidden="true"></div>
            <div class="analysis-insight-theme">
                <p>Top theme</p>
                <h4>${escapeHtml(label)}</h4>
                <span>${formatNumber(count)} mentions${escapeHtml(percentText)}</span>
            </div>
        </article>
    `;
}

function buildTopNgramInsight(item) {
    const term = normalizeValue(item.term) || "Repeated Language";
    const count = Number(item.document_count || item.count || 0);
    return `
        <article class="analysis-insight-card">
            <div class="analysis-insight-icon" aria-hidden="true">
                <span></span>
            </div>
            <div class="analysis-insight-copy">
                <p class="analysis-insight-kicker">Top Insight</p>
                <h3>${escapeHtml(term)} is the most repeated phrase.</h3>
                <p>${formatNumber(count)} response(s) include this word or phrase.</p>
            </div>
            <div class="analysis-insight-divider" aria-hidden="true"></div>
            <div class="analysis-insight-theme">
                <p>Top phrase</p>
                <h4>${escapeHtml(term)}</h4>
                <span>${formatNumber(count)} responses</span>
            </div>
        </article>
    `;
}

function findTopNgramItem(result) {
    const buckets = Array.isArray(result.ngram_buckets) ? result.ngram_buckets : [];
    return buckets
        .flatMap((bucket) => Array.isArray(bucket.items) ? bucket.items : [])
        .sort((left, right) => Number(right.document_count || right.count || 0) - Number(left.document_count || left.count || 0))[0] || null;
}

function displayAnalysisMethodLabel(modelKey) {
    if (modelKey === "community") {
        return "Topic Groups";
    }
    return displayAnalysisMode(modelKey);
}
