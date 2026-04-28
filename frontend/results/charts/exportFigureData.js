import { wrapPlotLabelTwoLines } from "../shared/utils.js";


const REPORT_EXPORT_MAX_BARS = 12;


export function limitAnalysisExportData(data, definition) {
    const kind = definition?.kind || "";
    if (kind !== "group" && kind !== "ngram") {
        return data;
    }

    return data.map((trace) => {
        if (!trace || trace.type !== "bar" || trace.orientation !== "h") {
            return trace;
        }

        return {
            ...trace,
            x: Array.isArray(trace.x) ? trace.x.slice(0, REPORT_EXPORT_MAX_BARS) : trace.x,
            y: Array.isArray(trace.y)
                ? trace.y
                    .slice(0, REPORT_EXPORT_MAX_BARS)
                    .map((label) => kind === "group"
                        ? wrapFullExportPlotLabel(label, 34)
                        : clampExportPlotLabel(label, 18))
                : trace.y,
            customdata: Array.isArray(trace.customdata) ? trace.customdata.slice(0, REPORT_EXPORT_MAX_BARS) : trace.customdata,
            text: Array.isArray(trace.text) ? trace.text.slice(0, REPORT_EXPORT_MAX_BARS) : trace.text,
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

    if (kind === "group") {
        return Math.max(1170, Math.min(fallbackHeight, barCount * 78 + 230));
    }

    const barHeight = 48;
    return Math.max(560, Math.min(fallbackHeight, barCount * barHeight + 180));
}


export function clonePlotlyFigureValue(value) {
    if (value === null || value === undefined) {
        return value;
    }
    return JSON.parse(JSON.stringify(value));
}


function clampExportPlotLabel(label, maxLineLength = 18) {
    const normalized = `${label || ""}`
        .replaceAll("<br>", " ")
        .replace(/\s+/g, " ")
        .trim();
    return wrapPlotLabelTwoLines(normalized, maxLineLength);
}


function wrapFullExportPlotLabel(label, maxLineLength = 34) {
    const words = `${label || ""}`
        .replaceAll("<br>", " ")
        .replace(/\s+/g, " ")
        .trim()
        .split(" ")
        .filter(Boolean);
    if (!words.length) {
        return "Untitled";
    }

    const lines = [];
    let currentLine = "";
    for (const word of words) {
        const nextLine = currentLine ? `${currentLine} ${word}` : word;
        if (nextLine.length <= maxLineLength || !currentLine) {
            currentLine = nextLine;
            continue;
        }
        lines.push(currentLine);
        currentLine = word;
    }
    if (currentLine) {
        lines.push(currentLine);
    }
    return lines.join("<br>");
}
