import { beforeEach, describe, expect, it } from "vitest";
import {
    applyDatasetPayload,
    resetDatasetState,
    resetState,
    setActiveFilters,
    setAnalysisResult,
    setAnalysisRunning,
    setAnalysisSelection,
    setCurrentWorkspace,
    setResultIdentity,
    setSelectedFilter,
    state,
} from "./state.js";

describe("results/shared/state", () => {
    beforeEach(() => {
        resetState();
    });

    it("keeps flat compatibility aliases in sync with grouped state", () => {
        setResultIdentity({ filename: "survey.csv" }, "result-123");
        setAnalysisSelection({ column: "comment", model: "ngrams" });
        setAnalysisRunning(true);

        expect(state.resultId).toBe("result-123");
        expect(state.result.id).toBe("result-123");
        expect(state.selectedAnalysisColumn).toBe("comment");
        expect(state.analysis.selectedColumn).toBe("comment");
        expect(state.analysisRunning).toBe(true);

        state.analysisRunning = false;

        expect(state.analysis.running).toBe(false);
    });

    it("groups filter and workspace mutations", () => {
        const filters = { country: ["UK"] };

        setSelectedFilter({ column: "country", value: "UK" });
        setActiveFilters(filters);
        setCurrentWorkspace("analysis-results");
        filters.country.push("US");

        expect(state.filters.selectedColumn).toBe("country");
        expect(state.selectedFilterValue).toBe("UK");
        expect(state.activeFilters).toEqual({ country: ["UK"] });
        expect(state.currentWorkspace).toBe("analysis-results");
    });

    it("stores analysis results through a mutation helper", () => {
        const payload = { ok: true, model_key: "community" };

        setAnalysisResult(payload);

        expect(state.analysis.result).toBe(payload);
        expect(state.analysisResult).toBe(payload);
    });

    it("applies row dataset payloads to the grouped data state", () => {
        applyDatasetPayload("analysis", {
            rows: [{ comment: "Useful" }],
            has_more: true,
            total_row_count: 10,
            unfiltered_row_count: 12,
            column_names: ["comment"],
        });

        expect(state.dataset.analysis.rows).toEqual([{ comment: "Useful" }]);
        expect(state.analysisRows).toEqual([{ comment: "Useful" }]);
        expect(state.analysisHasMore).toBe(true);
        expect(state.analysisTotalRows).toBe(10);
        expect(state.analysisUnfilteredTotalRows).toBe(12);
        expect(state.analysisColumnNames).toEqual(["comment"]);
    });

    it("resets a single row dataset without clearing unrelated state", () => {
        applyDatasetPayload("transformed", {
            rows: [{ comment: "Useful" }],
            has_more: true,
            total_row_count: 10,
            unfiltered_row_count: 10,
            column_names: ["comment"],
        });
        setAnalysisRunning(true);

        resetDatasetState("transformed");

        expect(state.transformedRows).toEqual([]);
        expect(state.transformedHasMore).toBe(false);
        expect(state.transformedTotalRows).toBe(0);
        expect(state.analysisRunning).toBe(true);
    });
});
