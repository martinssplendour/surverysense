import {
    EXPORT_BAR_GAP,
    GROUP_EXPORT_FONT_SIZE,
    GROUP_EXPORT_LABEL_FONT_SIZE,
    NGRAM_EXPORT_FONT_SIZE,
    setExportFontSize,
} from "./exportTypography.js";


export function buildAnalysisExportLayoutOverrides(definition, baseLayout) {
    const kind = definition?.kind || "";
    const ngramSize = Number(definition?.ngramSize || 0);
    const baseMargin = baseLayout?.margin || {};
    const baseFont = baseLayout?.font || {};
    const baseXAxis = baseLayout?.xaxis || {};
    const baseYAxis = baseLayout?.yaxis || {};

    const overrides = {
        paper_bgcolor: "#ffffff",
        title: {
            ...(baseLayout?.title || {}),
            text: "",
        },
    };

    if (kind === "ngram") {
        const exportLeftMargin = ngramSize === 3 ? 286 : 268;
        overrides.margin = {
            ...baseMargin,
            l: Math.max(Number(baseMargin.l || 0), exportLeftMargin),
            r: Math.max(Number(baseMargin.r || 0), 48),
            t: Math.max(Number(baseMargin.t || 0), 52),
            b: Math.max(Number(baseMargin.b || 0), 124),
        };
        overrides.bargap = EXPORT_BAR_GAP;
        overrides.font = setExportFontSize(baseFont, NGRAM_EXPORT_FONT_SIZE);
        overrides.xaxis = {
            ...baseXAxis,
            title: {
                ...(baseXAxis && typeof baseXAxis.title === "object" ? baseXAxis.title : {}),
                text: "Number of occurrences",
                standoff: 18,
                font: setExportFontSize(
                    (baseXAxis && typeof baseXAxis.title === "object" && typeof baseXAxis.title.font === "object")
                        ? baseXAxis.title.font
                        : {},
                    NGRAM_EXPORT_FONT_SIZE,
                ),
            },
            tickfont: setExportFontSize(baseXAxis.tickfont || {}, NGRAM_EXPORT_FONT_SIZE),
        };
        overrides.yaxis = {
            ...baseYAxis,
            title: {
                ...(baseYAxis && typeof baseYAxis.title === "object" ? baseYAxis.title : {}),
                text: "",
            },
            automargin: true,
            tickangle: 0,
            tickfont: setExportFontSize(baseYAxis.tickfont || {}, NGRAM_EXPORT_FONT_SIZE),
        };
        if (baseLayout?.uniformtext && typeof baseLayout.uniformtext === "object") {
            overrides.uniformtext = {
                ...baseLayout.uniformtext,
                minsize: NGRAM_EXPORT_FONT_SIZE,
            };
        }
    }

    if (kind === "group") {
        overrides.margin = {
            ...baseMargin,
            l: Math.max(Number(baseMargin.l || 0), 404),
            r: Math.max(Number(baseMargin.r || 0), 72),
            t: Math.max(Number(baseMargin.t || 0), 52),
            b: Math.max(Number(baseMargin.b || 0), 92),
        };
        overrides.bargap = EXPORT_BAR_GAP;
        overrides.font = setExportFontSize(baseFont, GROUP_EXPORT_FONT_SIZE);
        overrides.xaxis = {
            ...baseXAxis,
            title: {
                ...(baseXAxis && typeof baseXAxis.title === "object" ? baseXAxis.title : {}),
                standoff: 18,
                font: setExportFontSize(
                    (baseXAxis && typeof baseXAxis.title === "object" && typeof baseXAxis.title.font === "object")
                        ? baseXAxis.title.font
                        : {},
                    GROUP_EXPORT_FONT_SIZE,
                ),
            },
            tickfont: setExportFontSize(baseXAxis.tickfont || {}, GROUP_EXPORT_FONT_SIZE),
        };
        overrides.yaxis = {
            ...baseYAxis,
            automargin: true,
            tickangle: 0,
            title: {
                ...(baseYAxis && typeof baseYAxis.title === "object" ? baseYAxis.title : {}),
                text: "",
                font: setExportFontSize(
                    (baseYAxis && typeof baseYAxis.title === "object" && typeof baseYAxis.title.font === "object")
                        ? baseYAxis.title.font
                        : {},
                    GROUP_EXPORT_FONT_SIZE,
                ),
            },
            tickfont: setExportFontSize(baseYAxis.tickfont || {}, GROUP_EXPORT_LABEL_FONT_SIZE),
        };
        if (baseLayout?.uniformtext && typeof baseLayout.uniformtext === "object") {
            overrides.uniformtext = {
                ...baseLayout.uniformtext,
                minsize: GROUP_EXPORT_FONT_SIZE,
            };
        }
    }

    return overrides;
}
