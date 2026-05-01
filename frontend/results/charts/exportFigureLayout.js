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
        const exportLeftMargin = ngramSize === 3 ? 190 : 172;
        overrides.margin = {
            ...baseMargin,
            l: Math.max(Number(baseMargin.l || 0), exportLeftMargin),
            r: Math.max(Number(baseMargin.r || 0), 12),
            t: Math.max(Number(baseMargin.t || 0), 44),
            b: Math.max(Number(baseMargin.b || 0), 40),
        };
        overrides.font = {
            ...baseFont,
            size: Math.max(Number(baseFont.size || 0), 12),
        };
        overrides.xaxis = {
            ...baseXAxis,
            title: {
                ...(baseXAxis && typeof baseXAxis.title === "object" ? baseXAxis.title : {}),
                font: {
                    ...((baseXAxis && typeof baseXAxis.title === "object" && typeof baseXAxis.title.font === "object")
                        ? baseXAxis.title.font
                        : {}),
                    size: 16,
                },
            },
            tickfont: {
                ...(baseXAxis.tickfont || {}),
                size: Math.max(Number(baseXAxis?.tickfont?.size || 0), 15),
            },
        };
        overrides.yaxis = {
            ...baseYAxis,
            title: {
                ...(baseYAxis && typeof baseYAxis.title === "object" ? baseYAxis.title : {}),
                text: "",
            },
            automargin: true,
            tickangle: 0,
            tickfont: {
                ...(baseYAxis.tickfont || {}),
                size: ngramSize === 2 || ngramSize === 3 ? 12 : 24,
            },
        };
    }

    if (kind === "group") {
        overrides.margin = {
            ...baseMargin,
            l: Math.max(Number(baseMargin.l || 0), 292),
            r: Math.max(Number(baseMargin.r || 0), 46),
            t: Math.max(Number(baseMargin.t || 0), 44),
            b: Math.max(Number(baseMargin.b || 0), 76),
        };
        overrides.font = {
            ...baseFont,
            size: Math.max(Number(baseFont.size || 0), 16),
        };
        overrides.xaxis = {
            ...baseXAxis,
            title: {
                ...(baseXAxis && typeof baseXAxis.title === "object" ? baseXAxis.title : {}),
                standoff: 18,
                font: {
                    ...((baseXAxis && typeof baseXAxis.title === "object" && typeof baseXAxis.title.font === "object")
                        ? baseXAxis.title.font
                        : {}),
                    size: 16,
                },
            },
            tickfont: {
                ...(baseXAxis.tickfont || {}),
                size: Math.max(Number(baseXAxis?.tickfont?.size || 0), 16),
            },
        };
        overrides.yaxis = {
            ...baseYAxis,
            automargin: true,
            tickangle: 0,
            title: {
                ...(baseYAxis && typeof baseYAxis.title === "object" ? baseYAxis.title : {}),
                text: "",
                font: {
                    ...((baseYAxis && typeof baseYAxis.title === "object" && typeof baseYAxis.title.font === "object")
                        ? baseYAxis.title.font
                        : {}),
                    size: 16,
                },
            },
            tickfont: {
                ...(baseYAxis.tickfont || {}),
                size: Math.max(Number(baseYAxis?.tickfont?.size || 0), 18),
            },
        };
    }

    return overrides;
}
