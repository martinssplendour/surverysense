import {
    GROUP_EXPORT_LABEL_FONT_SIZE,
    GROUP_EXPORT_FONT_SIZE,
    NGRAM_EXPORT_FONT_SIZE,
    resolveExportBarRowHeight,
    setExportFontSize,
    wrapExportPlotLabelTwoLines,
} from "./exportTypography.js";


const REPORT_EXPORT_MAX_BARS = 10;
const GROUP_EXPORT_VERTICAL_MARGIN = 122;
const NGRAM_EXPORT_VERTICAL_MARGIN = 142;


export function limitAnalysisExportData(data, definition) {
    const kind = definition?.kind || "";
    if (kind !== "group" && kind !== "ngram") {
        return data;
    }

    return data.map((trace) => {
        if (!trace || trace.type !== "bar" || trace.orientation !== "h") {
            return trace;
        }
        const exportTextFontSize = kind === "group" ? GROUP_EXPORT_FONT_SIZE : NGRAM_EXPORT_FONT_SIZE;

        return {
            ...trace,
            x: Array.isArray(trace.x) ? trace.x.slice(0, REPORT_EXPORT_MAX_BARS) : trace.x,
            y: Array.isArray(trace.y)
                ? trace.y
                    .slice(0, REPORT_EXPORT_MAX_BARS)
                    .map((label) => kind === "group"
                        ? wrapExportPlotLabelTwoLines(label, 24)
                        : wrapExportPlotLabelTwoLines(label, 18))
                : trace.y,
            customdata: Array.isArray(trace.customdata) ? trace.customdata.slice(0, REPORT_EXPORT_MAX_BARS) : trace.customdata,
            text: Array.isArray(trace.text) ? trace.text.slice(0, REPORT_EXPORT_MAX_BARS) : trace.text,
            textfont: setExportFontSize(trace.textfont, exportTextFontSize),
            insidetextfont: setExportFontSize(trace.insidetextfont, exportTextFontSize),
            outsidetextfont: setExportFontSize(trace.outsidetextfont, exportTextFontSize),
            hovertext: Array.isArray(trace.hovertext) ? trace.hovertext.slice(0, REPORT_EXPORT_MAX_BARS) : trace.hovertext,
        };
    });
}


export function resolveAnalysisExportHeight({ data, definition, fallbackHeight }) {
    const kind = definition?.kind || "";
    if (kind !== "group" && kind !== "ngram") {
        return fallbackHeight;
    }

    const firstBarTrace = Array.isArray(data)
        ? data.find((trace) => trace && trace.type === "bar" && trace.orientation === "h")
        : null;
    const barCount = Array.isArray(firstBarTrace?.y) ? firstBarTrace.y.length : 0;
    if (!barCount) {
        return fallbackHeight;
    }

    return resolveBarChartExportHeight({
        kind,
        barCount,
        fallbackHeight,
    });
}


export function resolveBarChartExportHeight({ kind, barCount, fallbackHeight }) {
    const normalizedKind = kind === "group" ? "group" : kind === "ngram" ? "ngram" : "";
    const normalizedBarCount = Math.max(0, Number(barCount || 0));
    if (!normalizedKind || !normalizedBarCount) {
        return fallbackHeight;
    }

    const verticalMargin = normalizedKind === "group"
        ? GROUP_EXPORT_VERTICAL_MARGIN
        : NGRAM_EXPORT_VERTICAL_MARGIN;
    const labelFontSize = normalizedKind === "group"
        ? GROUP_EXPORT_LABEL_FONT_SIZE
        : NGRAM_EXPORT_FONT_SIZE;
    const computedHeight = verticalMargin + normalizedBarCount * resolveExportBarRowHeight(labelFontSize);
    const numericFallbackHeight = Number(fallbackHeight || 0);
    if (!Number.isFinite(numericFallbackHeight) || numericFallbackHeight <= 0) {
        return computedHeight;
    }
    return Math.min(numericFallbackHeight, computedHeight);
}


export function clonePlotlyFigureValue(value) {
    if (value === null || value === undefined) {
        return value;
    }
    return JSON.parse(JSON.stringify(value));
}
