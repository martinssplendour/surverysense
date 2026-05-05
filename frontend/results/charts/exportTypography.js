import { wrapPlotLabelTwoLines } from "../shared/utils.js";


const SMALL_EXPORT_FONT_THRESHOLD = 20;
const SMALL_EXPORT_FONT_SCALE = 1.75;

export const NGRAM_EXPORT_FONT_SIZE = 19;
export const GROUP_EXPORT_FONT_SIZE = 19;
export const GROUP_EXPORT_LABEL_FONT_SIZE = 19;
export const EXPORT_MAX_LABEL_LINES = 2;
export const EXPORT_BAR_THICKNESS_MULTIPLIER = 3;
export const EXPORT_BAR_GAP = 0.12;
export const EXPORT_BAR_LABEL_PADDING = 8;


export function scaleSmallExportFontSize(size, minimum = 0) {
    const numericSize = Number(size || 0);
    if (numericSize <= 0) {
        return Math.max(0, Number(minimum || 0));
    }
    const resolvedSize = numericSize <= SMALL_EXPORT_FONT_THRESHOLD
        ? Math.round(numericSize * SMALL_EXPORT_FONT_SCALE)
        : Math.round(numericSize);
    return Math.max(resolvedSize, Number(minimum || 0));
}


export function scaleSmallExportFont(font, minimum = 0) {
    const resolvedFont = font && typeof font === "object" ? font : {};
    return {
        ...resolvedFont,
        size: scaleSmallExportFontSize(resolvedFont.size, minimum),
    };
}


export function setExportFontSize(font, size) {
    const resolvedFont = font && typeof font === "object" ? font : {};
    return {
        ...resolvedFont,
        size: Math.max(0, Number(size || 0)),
    };
}


export function resolveExportBarThickness(fontSize) {
    const numericFontSize = Math.max(0, Number(fontSize || 0));
    return Math.ceil(numericFontSize * EXPORT_BAR_THICKNESS_MULTIPLIER + EXPORT_BAR_LABEL_PADDING);
}


export function resolveExportBarRowHeight(fontSize) {
    const targetBarThickness = resolveExportBarThickness(fontSize);
    const usableHeightShare = Math.max(0.01, 1 - EXPORT_BAR_GAP);
    return Math.ceil(targetBarThickness / usableHeightShare);
}


export function wrapExportPlotLabelTwoLines(value, maxLineLength = 18) {
    const normalized = `${value || ""}`
        .replaceAll("<br>", " ")
        .replace(/\s+/g, " ")
        .trim();
    return wrapPlotLabelTwoLines(normalized, maxLineLength);
}
