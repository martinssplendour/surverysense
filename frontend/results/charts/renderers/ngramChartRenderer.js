import { elements } from "../../shared.js";
import { escapeHtml, formatNumber, normalizeValue } from "../../shared/utils.js";


const MAX_ITEMS_PER_NGRAM_CHART = 10;


export function renderNgramFrequencyCharts(buckets, { openAnalysisNgramModal }) {
    elements.analysisChart.hidden = false;
    elements.analysisChart.innerHTML = `
        <div class="analysis-chart-copy">
            <h4 class="analysis-chart-title">Most common words and phrases in the selected responses</h4>
            <p class="analysis-chart-caption">Click a row to open the matching responses.</p>
        </div>
        <div class="analysis-plot-grid analysis-ngram-plot-grid">
            ${buckets.map((bucket, bucketIndex) => buildNgramColumn(bucket, bucketIndex)).join("")}
        </div>
    `;

    elements.analysisChart.querySelectorAll("[data-ngram-bucket]").forEach((button) => {
        button.addEventListener("click", () => {
            const bucketIndex = Number(button.dataset.ngramBucket);
            const itemIndex = Number(button.dataset.ngramItem);
            if (Number.isFinite(bucketIndex) && Number.isFinite(itemIndex)) {
                openAnalysisNgramModal(bucketIndex, itemIndex);
            }
        });
    });
}


function buildNgramColumn(bucket, bucketIndex) {
    const label = bucket.label || `${bucket.ngram_size}-grams`;
    const items = Array.isArray(bucket.items) ? bucket.items.slice(0, MAX_ITEMS_PER_NGRAM_CHART) : [];
    const maxCount = Math.max(...items.map((item) => Number(item.count || 0)), 1);

    return `
        <div class="analysis-ngram-column">
            <h4 class="analysis-ngram-column-title">${escapeHtml(label)}</h4>
            <div class="analysis-ngram-list">
                ${items.map((item, itemIndex) => buildNgramRow(item, itemIndex, bucketIndex, maxCount)).join("")}
            </div>
        </div>
    `;
}


function buildNgramRow(item, itemIndex, bucketIndex, maxCount) {
    const term = normalizeValue(item.term || "");
    const count = Number(item.count || 0);
    const width = Math.max(4, Math.round((count / maxCount) * 100));

    return `
        <button type="button" class="analysis-ngram-row"
            data-ngram-bucket="${bucketIndex}"
            data-ngram-item="${itemIndex}"
            title="${escapeHtml(term)}">
            <span class="analysis-ngram-name">${escapeHtml(term)}</span>
            <span class="analysis-theme-bar-track" aria-hidden="true">
                <span class="analysis-theme-bar-fill" style="width:${width}%"></span>
            </span>
            <span class="analysis-ngram-count">${formatNumber(count)}</span>
        </button>
    `;
}
