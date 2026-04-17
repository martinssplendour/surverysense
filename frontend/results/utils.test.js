import { beforeAll, describe, expect, it } from "vitest";

let buildExampleRowLabel;
let buildPercentLabel;
let escapeHtml;
let normalizeValue;
let parseDownloadFilename;
let wrapPlotLabel;
let wrapPlotLabelTwoLines;

beforeAll(async () => {
    globalThis.document = {
        getElementById: () => null,
        querySelector: () => null,
    };

    ({
        buildExampleRowLabel,
        buildPercentLabel,
        escapeHtml,
        normalizeValue,
        parseDownloadFilename,
        wrapPlotLabel,
        wrapPlotLabelTwoLines,
    } = await import("./utils.js"));
});

describe("results/utils", () => {
    it("escapes HTML-sensitive characters", () => {
        expect(escapeHtml(`<script>alert("x")</script>`)).toBe(
            "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;",
        );
    });

    it("normalizes nullish values to an empty string", () => {
        expect(normalizeValue(null)).toBe("");
        expect(normalizeValue(undefined)).toBe("");
        expect(normalizeValue("  kept  ")).toBe("kept");
    });

    it("builds a representative row label from row numbers", () => {
        expect(
            buildExampleRowLabel([
                { row_number: 4 },
                { row_number: 8 },
            ]),
        ).toBe("Row 4, Row 8");
    });

    it("parses filenames from content-disposition headers", () => {
        expect(parseDownloadFilename('attachment; filename="report.pdf"')).toBe("report.pdf");
    });

    it("formats percent labels from numeric shares", () => {
        expect(buildPercentLabel(0.326)).toBe("33%");
        expect(buildPercentLabel(Number.NaN)).toBe("Not available");
    });

    it("wraps long plot labels into HTML line breaks", () => {
        expect(wrapPlotLabel("This is a deliberately long chart label", 12)).toContain("<br>");
        expect(wrapPlotLabel("", 12)).toBe("Untitled");
    });

    it("splits topic labels across exactly two lines", () => {
        expect(wrapPlotLabelTwoLines("Editable And Diverse Resources")).toBe("Editable And<br>Diverse Resources");
        expect(wrapPlotLabelTwoLines("Single")).toBe("Single");
        expect(wrapPlotLabelTwoLines("")).toBe("Untitled");
    });
});
