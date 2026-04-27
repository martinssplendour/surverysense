import { elements } from "./shared.js";
import {
    buildPercentLabel,
    escapeHtml,
    formatNumber,
    normalizeValue,
} from "./shared/utils.js";


export function renderGroupDistributionChart(groups, { controlsHtml = "", openAnalysisGroupModalByIndex }) {
    elements.analysisChart.hidden = false;
    const sortedGroups = groups
        .map((group, index) => ({ group, index }))
        .sort((left, right) => Number(right.group.count || 0) - Number(left.group.count || 0));
    const maxCount = Math.max(...sortedGroups.map(({ group }) => Number(group.count || 0)), 1);

    elements.analysisChart.innerHTML = `
        <div class="analysis-theme-card-header">
            <div class="analysis-chart-copy">
                <h4 class="analysis-chart-title">Top themes</h4>
                <p class="analysis-chart-caption">Click a theme to view example responses</p>
            </div>
            ${controlsHtml}
        </div>
        <div class="analysis-theme-list">
            ${sortedGroups
                .map(({ group, index }) => buildThemeRow(group, index, maxCount))
                .join("")}
        </div>
    `;

    elements.analysisChart.querySelectorAll("[data-analysis-group-index]").forEach((button) => {
        if (!(button instanceof HTMLButtonElement)) {
            return;
        }
        button.addEventListener("click", () => {
            const groupIndex = Number(button.dataset.analysisGroupIndex);
            if (Number.isFinite(groupIndex)) {
                openAnalysisGroupModalByIndex(groupIndex);
            }
        });
    });
}


function buildThemeRow(group, index, maxCount) {
    const label = normalizeValue(group.label) || "Untitled theme";
    const count = Number(group.count || 0);
    const width = Math.max(4, Math.round((count / maxCount) * 100));
    const percent = buildPercentLabel(group.share);
    const percentLabel = percent === "Not available" ? "-" : percent;
    const noiseClass = group.is_noise ? " analysis-theme-bar-fill-noise" : "";

    return `
        <button type="button" class="analysis-theme-row" data-analysis-group-index="${index}">
            <span class="analysis-theme-name">${escapeHtml(label)}</span>
            <span class="analysis-theme-bar-cell" aria-hidden="true">
                <span class="analysis-theme-bar-track">
                    <span class="analysis-theme-bar-fill${noiseClass}" style="width:${width}%"></span>
                </span>
            </span>
            <span class="analysis-theme-count">${formatNumber(count)}</span>
            <span class="analysis-theme-percent">${escapeHtml(percentLabel)}</span>
            <span class="analysis-theme-chevron" aria-hidden="true">&rsaquo;</span>
        </button>
    `;
}
