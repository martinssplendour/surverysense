// Pure utility functions: HTML escaping, number formatting, column label display, and Plotly label wrapping.
import { ANALYSIS_MODE_OPTIONS } from "./constants.js";

export function summaryMetric(kind, label, value) {
    return `
        <div class="dashboard-metric">
            <div class="dashboard-metric-top">
                <span class="dashboard-metric-icon" aria-hidden="true">${dashboardMetricIcon(kind)}</span>
                <span class="dashboard-metric-value">${escapeHtml(value)}</span>
            </div>
            <span class="dashboard-metric-label">${escapeHtml(label)}</span>
        </div>
    `;
}

export function formatNumber(value) {
    const numericValue = Number(value || 0);
    return new Intl.NumberFormat("en-GB").format(numericValue);
}

export function normalizeValue(value) {
    if (value === null || value === undefined) {
        return "";
    }
    return `${value}`.trim();
}

export function formatCell(value) {
    const normalized = normalizeValue(value);
    return normalized ? escapeHtml(normalized) : "<span class=\"empty-cell\">-</span>";
}

export function escapeHtml(value) {
    return `${value}`
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll("\"", "&quot;")
        .replaceAll("'", "&#39;");
}

// Strips the internal deduplication suffix (e.g. "__idx_2") that the backend appends to duplicate column names.
export function displayColumnLabel(value) {
    return `${value}`.replace(/__idx_\d+$/i, "");
}

export function displayAnalysisMode(modelKey) {
    return ANALYSIS_MODE_OPTIONS.find((option) => option.key === modelKey)?.label || modelKey;
}

export function stripFilenameExtension(value) {
    const normalized = `${value || ""}`.trim();
    if (!normalized.includes(".")) {
        return normalized;
    }
    return normalized.replace(/\.[^/.]+$/, "");
}

export function slugify(value) {
    return `${value || ""}`
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "");
}

export function parseDownloadFilename(contentDisposition) {
    if (!contentDisposition) {
        return "";
    }
    const match = contentDisposition.match(/filename=\"?([^\";]+)\"?/i);
    return match ? match[1] : "";
}

export function buildPercentLabel(share) {
    if (typeof share !== "number" || Number.isNaN(share)) {
        return "Not available";
    }
    return `${Math.round(share * 100)}%`;
}

export function buildExampleRowLabel(examples) {
    if (!Array.isArray(examples) || !examples.length) {
        return "No representative rows";
    }

    const labels = examples
        .map((example) => Number(example.row_number || 0))
        .filter((rowNumber) => rowNumber > 0)
        .map((rowNumber) => `Row ${rowNumber}`);

    return labels.length ? labels.join(", ") : "No representative rows";
}

export function wrapPlotLabel(value, maxLineLength = 28) {
    const words = normalizeValue(value).split(/\s+/).filter(Boolean);
    if (!words.length) {
        return "Untitled";
    }

    const lines = [];
    let currentLine = "";
    words.forEach((word) => {
        const nextValue = currentLine ? `${currentLine} ${word}` : word;
        if (nextValue.length <= maxLineLength || !currentLine) {
            currentLine = nextValue;
            return;
        }
        lines.push(currentLine);
        currentLine = word;
    });

    if (currentLine) {
        lines.push(currentLine);
    }

    return lines.join("<br>");
}

function truncatePlotLabelLine(value, maxLineLength) {
    const normalized = normalizeValue(value);
    if (!normalized) {
        return "";
    }
    if (normalized.length <= maxLineLength) {
        return normalized;
    }
    return `${normalized.slice(0, Math.max(1, maxLineLength - 3)).trimEnd()}...`;
}

/**
 * Wraps a plot label into at most two lines separated by Plotly's "<br>" newline token.
 * Prefers balanced lines, but caps each line length so long labels do not overflow the chart margin.
 */
export function wrapPlotLabelTwoLines(value, maxLineLength = 18) {
    const words = normalizeValue(value).split(/\s+/).filter(Boolean);
    if (!words.length) {
        return "Untitled";
    }
    if (words.length === 1) {
        return truncatePlotLabelLine(words[0], maxLineLength);
    }

    let bestSplitIndex = 1;
    let bestScore = Number.POSITIVE_INFINITY;
    for (let index = 1; index < words.length; index += 1) {
        const firstLine = words.slice(0, index).join(" ");
        const secondLine = words.slice(index).join(" ");
        const firstOverflow = Math.max(0, firstLine.length - maxLineLength);
        const secondOverflow = Math.max(0, secondLine.length - maxLineLength);
        const overflowScore = firstOverflow * 1000 + secondOverflow * 100;
        const balanceScore = Math.abs(firstLine.length - secondLine.length);
        const score = overflowScore + balanceScore;
        if (score < bestScore) {
            bestScore = score;
            bestSplitIndex = index;
        }
    }

    const firstLine = truncatePlotLabelLine(words.slice(0, bestSplitIndex).join(" "), maxLineLength);
    const secondLine = truncatePlotLabelLine(words.slice(bestSplitIndex).join(" "), maxLineLength);
    return secondLine ? `${firstLine}<br>${secondLine}` : firstLine;
}

function dashboardMetricIcon(kind) {
    const icons = {
        rows: `
            <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
                <rect x="3" y="5" width="18" height="16" rx="2"></rect>
                <path d="M3 10.5h18M8.5 10.5V21M15.5 10.5V21"></path>
                <path d="M3 15.75h18"></path>
                <path d="M7 3.5h10"></path>
            </svg>
        `,
        columns: `
            <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
                <rect x="3" y="5" width="18" height="14" rx="2"></rect>
                <path d="M9 5v14M15 5v14"></path>
                <path d="M3 10h18M3 14h18"></path>
            </svg>
        `,
        verbatim: `
            <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
                <path d="M6 5h12a3 3 0 0 1 3 3v6a3 3 0 0 1-3 3h-6l-4.5 3V17H6a3 3 0 0 1-3-3V8a3 3 0 0 1 3-3Z"></path>
                <path d="M8 9.5h8M8 12.5h6"></path>
            </svg>
        `,
    };
    return icons[kind] || "";
}
