import {
    EXPORT_BAR_GAP,
    GROUP_EXPORT_FONT_SIZE,
    GROUP_EXPORT_LABEL_FONT_SIZE,
    NGRAM_EXPORT_FONT_SIZE,
    wrapExportPlotLabelTwoLines,
} from "../exportTypography.js";

const MAX_GENERATED_NGRAM_BARS = 10;
const EXPORT_LABEL_XSHIFT = -10;
const EXPORT_LABEL_LINE_OFFSET_SCALE = 0.5;

export function normalizeNgramItems(items) {
    return Array.isArray(items)
        ? [...items]
            .map((item) => ({
                ...item,
                count: Number(item.count || 0),
                document_count: Number(item.document_count || 0),
                term: `${item.term || ""}`.trim(),
            }))
            .filter((item) => item.term && item.count > 0)
            .sort((left, right) => right.count - left.count)
            .slice(0, MAX_GENERATED_NGRAM_BARS)
        : [];
}

export function buildGeneratedGroupBarData(groups) {
    return [
        {
            type: "bar",
            orientation: "h",
            y: groups.map((group) => wrapExportPlotLabelTwoLines(group.label || "Unlabelled theme", 24)),
            x: groups.map((group) => Number(group.count || 0)),
            text: groups.map((group) => String(Number(group.count || 0))),
            textposition: "outside",
            textfont: {
                size: GROUP_EXPORT_FONT_SIZE,
                color: "#172033",
            },
            cliponaxis: false,
            marker: {
                color: groups.map((group) => group.is_noise ? "#9aa4b2" : "#2477F8"),
                line: {
                    color: groups.map((group) => group.is_noise ? "#818b98" : "#1b5dcc"),
                    width: 1,
                },
            },
            hovertemplate: [
                "<b>%{y}</b>",
                "Number of responses: %{x}",
                "<extra></extra>",
            ].join("<br>"),
        },
    ];
}

export function buildGeneratedNgramBarData(items) {
    return [
        {
            type: "bar",
            orientation: "h",
            y: items.map((item) => wrapExportPlotLabelTwoLines(item.term, 22)),
            x: items.map((item) => item.count),
            text: items.map((item) => String(item.count)),
            textposition: "outside",
            textfont: {
                size: NGRAM_EXPORT_FONT_SIZE,
                color: "#172033",
            },
            cliponaxis: false,
            customdata: items.map((item) => [item.document_count]),
            marker: {
                color: "#2477F8",
                line: {
                    color: "#1b5dcc",
                    width: 1,
                },
            },
            hovertemplate: [
                "<b>%{y}</b>",
                "Number of occurrences: %{x}",
                "Matching responses: %{customdata[0]}",
                "<extra></extra>",
            ].join("<br>"),
        },
    ];
}

function buildExportYAxisLabelAnnotations(labels, fontSize) {
    return labels.flatMap((label) => {
        const lines = String(label || "")
            .split("<br>")
            .map((part) => part.trim())
            .filter(Boolean)
            .slice(0, 2);
        if (!lines.length) {
            return [];
        }

        const lineOffset = lines.length > 1
            ? Math.max(4, Math.round(Number(fontSize || 0) * EXPORT_LABEL_LINE_OFFSET_SCALE))
            : 0;

        return lines.map((line, index) => ({
            x: 0,
            xref: "paper",
            xanchor: "right",
            xshift: EXPORT_LABEL_XSHIFT,
            y: label,
            yref: "y",
            yshift: lines.length > 1
                ? (index === 0 ? lineOffset : -lineOffset)
                : 0,
            text: line,
            showarrow: false,
            align: "right",
            font: {
                family: "\"Segoe UI\", Aptos, sans-serif",
                size: fontSize,
                color: "#172033",
            },
        }));
    });
}

export function buildGeneratedGroupBarLayout(groups, { width, height }) {
    const maxCount = Math.max(...groups.map((group) => Number(group.count || 0)), 1);
    const wrappedLabels = groups.map((group) => wrapExportPlotLabelTwoLines(group.label || "Unlabelled theme", 24));
    return {
        width,
        height,
        autosize: false,
        annotations: buildExportYAxisLabelAnnotations(wrappedLabels, GROUP_EXPORT_LABEL_FONT_SIZE),
        margin: {
            t: 30,
            r: 72,
            b: 92,
            l: 404,
        },
        paper_bgcolor: "rgba(0, 0, 0, 0)",
        plot_bgcolor: "#ffffff",
        font: {
            family: "\"Segoe UI\", Aptos, sans-serif",
            color: "#172033",
            size: GROUP_EXPORT_FONT_SIZE,
        },
        uniformtext: {
            minsize: GROUP_EXPORT_FONT_SIZE,
            mode: "show",
        },
        bargap: EXPORT_BAR_GAP,
        xaxis: {
            title: {
                text: "Number of responses",
                standoff: 18,
                font: {
                    size: GROUP_EXPORT_FONT_SIZE,
                },
            },
            tickfont: {
                size: GROUP_EXPORT_FONT_SIZE,
            },
            gridcolor: "rgba(89, 104, 128, 0.12)",
            zeroline: false,
            range: [0, Math.ceil(maxCount * 1.08)],
            fixedrange: true,
        },
        yaxis: {
            automargin: true,
            autorange: "reversed",
            tickangle: 0,
            showticklabels: false,
            tickfont: {
                size: GROUP_EXPORT_LABEL_FONT_SIZE,
            },
            fixedrange: true,
        },
    };
}

export function buildGeneratedNgramBarLayout(items, { width, height }) {
    const maxCount = Math.max(...items.map((item) => Number(item.count || 0)), 1);
    const wrappedLabels = items.map((item) => wrapExportPlotLabelTwoLines(item.term, 22));
    return {
        width,
        height,
        autosize: false,
        annotations: buildExportYAxisLabelAnnotations(wrappedLabels, NGRAM_EXPORT_FONT_SIZE),
        margin: {
            t: 30,
            r: 56,
            b: 112,
            l: 286,
        },
        paper_bgcolor: "rgba(0, 0, 0, 0)",
        plot_bgcolor: "#ffffff",
        font: {
            family: "\"Segoe UI\", Aptos, sans-serif",
            color: "#172033",
            size: NGRAM_EXPORT_FONT_SIZE,
        },
        uniformtext: {
            minsize: NGRAM_EXPORT_FONT_SIZE,
            mode: "show",
        },
        bargap: EXPORT_BAR_GAP,
        xaxis: {
            title: {
                text: "Number of occurrences",
                standoff: 18,
                font: {
                    size: NGRAM_EXPORT_FONT_SIZE,
                },
            },
            tickfont: {
                size: NGRAM_EXPORT_FONT_SIZE,
            },
            gridcolor: "rgba(89, 104, 128, 0.12)",
            zeroline: false,
            range: [0, Math.ceil(maxCount * 1.08)],
            fixedrange: true,
        },
        yaxis: {
            automargin: true,
            autorange: "reversed",
            tickangle: 0,
            showticklabels: false,
            tickfont: {
                size: NGRAM_EXPORT_FONT_SIZE,
            },
            fixedrange: true,
        },
    };
}
