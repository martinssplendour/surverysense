// Renders the top-theme/top-phrase insight summary for analysis results.
import { elements } from "../shared.js";
import {
    buildPercentLabel,
    escapeHtml,
    formatNumber,
    normalizeValue,
} from "../shared/utils.js";

export function renderAnalysisInsightSummary(result) {
    if (!elements.analysisSummary) {
        return;
    }

    const groups = Array.isArray(result.groups)
        ? result.groups.filter((group) => !group?.is_noise)
            .sort((left, right) => Number(right.count || 0) - Number(left.count || 0))
        : [];
    if (groups.length) {
        elements.analysisSummary.hidden = false;
        elements.analysisSummary.innerHTML = buildTopGroupInsight(groups[0], result);
        return;
    }

    const topNgramItem = findTopNgramItem(result);
    if (topNgramItem) {
        elements.analysisSummary.hidden = false;
        elements.analysisSummary.innerHTML = buildTopNgramInsight(topNgramItem, result);
        return;
    }

    if (getUnassignedCount(result) > 0) {
        elements.analysisSummary.hidden = false;
        elements.analysisSummary.innerHTML = buildUnassignedOnlyInsight(result);
        return;
    }

    elements.analysisSummary.innerHTML = "";
    elements.analysisSummary.hidden = true;
}


function buildTopGroupInsight(group, result) {
    const label = normalizeValue(group.label) || "Top Theme";
    const count = Number(group.count || 0);
    const percent = buildPercentLabel(group.share);
    const insightCopy = percent === "Not available"
        ? `${formatNumber(count)} response(s) mention this theme.`
        : `${percent} of responses mention this theme.`;

    const assignmentRing = buildAssignmentRing(result);

    return `
        <article class="analysis-insight-card${assignmentRing ? " analysis-insight-card-with-unassigned" : ""}">
            <div class="analysis-insight-icon" aria-hidden="true">
                <span></span>
            </div>
            <div class="analysis-insight-copy">
                <p class="analysis-insight-kicker">Top Theme</p>
                <h3>${escapeHtml(label)}</h3>
                <p>${escapeHtml(insightCopy)}</p>
            </div>
            ${assignmentRing}
            ${buildInsightRing(result)}
        </article>
    `;
}


function buildUnassignedOnlyInsight(result) {
    return `
        <article class="analysis-insight-card analysis-insight-card-unassigned-only">
            ${buildAssignmentRing(result)}
        </article>
    `;
}


function buildTopNgramInsight(item, result) {
    const term = normalizeValue(item.term) || "Repeated Language";
    const count = Number(item.document_count || item.count || 0);
    const assignmentRing = buildAssignmentRing(result);
    return `
        <article class="analysis-insight-card${assignmentRing ? " analysis-insight-card-with-unassigned" : ""}">
            <div class="analysis-insight-icon" aria-hidden="true">
                <span></span>
            </div>
            <div class="analysis-insight-copy">
                <p class="analysis-insight-kicker">Top Phrase</p>
                <h3>${escapeHtml(term)}</h3>
                <p>${formatNumber(count)} response(s) include this word or phrase.</p>
            </div>
            ${assignmentRing}
            ${buildInsightRing(result)}
        </article>
    `;
}

function buildAssignmentRing(result) {
    const { assigned, unassigned } = getAssignmentCounts(result);
    const unassignedCount = unassigned;
    if (!unassignedCount) {
        return "";
    }

    const total = assigned + unassignedCount;

    const r = 26;
    const circ = 2 * Math.PI * r;
    const assignedArc = total > 0 ? (assigned / total) * circ : 0;

    return `
        <div class="air-panel air-panel--assignment" aria-label="${formatNumber(assigned)} assigned responses, ${formatNumber(unassignedCount)} unassigned responses">
            <div class="air-donut">
                <svg viewBox="0 0 68 68" aria-hidden="true">
                    <circle class="air-track" cx="34" cy="34" r="${r}" />
                    <circle class="air-fill air-fill--assigned" cx="34" cy="34" r="${r}"
                        stroke-dasharray="${assignedArc.toFixed(2)} ${circ.toFixed(2)}"
                        transform="rotate(-90 34 34)" />
                </svg>
                <div class="air-center">
                    <span class="air-count">${formatNumber(unassignedCount)}</span>
                    <span class="air-sub">unassigned</span>
                </div>
            </div>
            <div class="air-legend">
                <div class="air-legend-row">
                    <span class="air-dot air-dot--assigned"></span>
                    <span class="air-legend-num">${formatNumber(assigned)}</span>
                    <span class="air-legend-label">Assigned</span>
                </div>
                <div class="air-legend-row">
                    <span class="air-dot air-dot--unassigned"></span>
                    <span class="air-legend-num">${formatNumber(unassignedCount)}</span>
                    <span class="air-legend-label">Unassigned</span>
                </div>
            </div>
        </div>
    `;
}


function getUnassignedCount(result) {
    const groups = Array.isArray(result.groups) ? result.groups : [];
    return groups
        .filter((group) => group?.is_noise)
        .reduce((total, group) => total + Number(group.count || 0), 0);
}

function getAssignmentCounts(result) {
    const groups = Array.isArray(result.groups) ? result.groups : [];
    const noiseGroupIds = new Set(
        groups
            .filter((group) => group?.is_noise)
            .map((group) => String(group.group_id)),
    );
    const points = Array.isArray(result.scatter_points) ? result.scatter_points : [];
    const assignedRows = new Set();
    const unassignedRows = new Set();

    for (const point of points) {
        const rowNumber = Number(point?.row_number || 0);
        if (!Number.isFinite(rowNumber) || rowNumber <= 0) {
            continue;
        }

        if (noiseGroupIds.has(String(point.group_id))) {
            if (!assignedRows.has(rowNumber)) {
                unassignedRows.add(rowNumber);
            }
            continue;
        }

        assignedRows.add(rowNumber);
        unassignedRows.delete(rowNumber);
    }

    if (assignedRows.size || unassignedRows.size) {
        return {
            assigned: assignedRows.size,
            unassigned: unassignedRows.size,
        };
    }

    return {
        assigned: groups
            .filter((group) => !group?.is_noise)
            .reduce((total, group) => total + Number(group.count || 0), 0),
        unassigned: getUnassignedCount(result),
    };
}


function buildInsightRing(result) {
    const skipped = Number(result.skipped_document_count || 0);
    const analyzed = Number(result.original_response_count || result.valid_document_count || 0);
    const total = skipped + analyzed;

    const r = 26;
    const circ = 2 * Math.PI * r;
    const analyzedArc = total > 0 ? (analyzed / total) * circ : circ;

    return `
        <div class="analysis-insight-divider" aria-hidden="true"></div>
        <div class="air-panel">
            <div class="air-donut">
                <svg viewBox="0 0 68 68" aria-hidden="true">
                    <circle class="air-track" cx="34" cy="34" r="${r}" />
                    <circle class="air-fill" cx="34" cy="34" r="${r}"
                        stroke-dasharray="${analyzedArc.toFixed(2)} ${circ.toFixed(2)}"
                        transform="rotate(-90 34 34)" />
                </svg>
                <div class="air-center">
                    <span class="air-count">${formatNumber(skipped)}</span>
                    <span class="air-sub">skipped</span>
                </div>
            </div>
            <div class="air-legend">
                <div class="air-legend-row">
                    <span class="air-dot air-dot--analyzed"></span>
                    <span class="air-legend-num">${formatNumber(analyzed)}</span>
                    <span class="air-legend-label">Analysed</span>
                </div>
                <div class="air-legend-row">
                    <span class="air-dot air-dot--skipped"></span>
                    <span class="air-legend-num">${formatNumber(skipped)}</span>
                    <span class="air-legend-label">Skipped</span>
                </div>
            </div>
        </div>
    `;
}


function findTopNgramItem(result) {
    const buckets = Array.isArray(result.ngram_buckets) ? result.ngram_buckets : [];
    return buckets
        .flatMap((bucket) => Array.isArray(bucket.items) ? bucket.items : [])
        .sort((left, right) => Number(right.document_count || right.count || 0) - Number(left.document_count || left.count || 0))[0] || null;
}
