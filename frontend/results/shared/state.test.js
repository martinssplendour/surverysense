import { beforeEach, describe, expect, it } from "vitest";
import {
    appendDatasetPayload,
    applyAnalysisGroupDocumentsPayload,
    applyResultPayload,
    applyDatasetPayload,
    resetDatasetState,
    resetState,
    resetStoredResultState,
    setActiveFilters,
    setAnalysisDocumentTranslation,
    setAnalysisDocumentTranslationLoading,
    setAnalysisExportState,
    setAnalysisGroupModalLoading,
    setAnalysisGroupModalUnavailable,
    setAnalysisResult,
    setAnalysisRunning,
    setAnalysisSelection,
    setDataExportState,
    setDatasetStatus,
    setPreviewState,
    setCurrentWorkspace,
    setResultIdentity,
    setSelectedFilter,
    state,
    syncResultResponseMetadata,
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

    it("appends row dataset payloads and updates dataset status", () => {
        applyDatasetPayload("analysis", {
            rows: [{ comment: "First" }],
            has_more: true,
            total_row_count: 2,
            unfiltered_row_count: 2,
            column_names: ["comment"],
        });
        setDatasetStatus("analysis", { loading: true });
        appendDatasetPayload("analysis", {
            rows: [{ comment: "Second" }],
            has_more: false,
            total_row_count: 2,
            unfiltered_row_count: 3,
        });

        expect(state.analysisRows).toEqual([{ comment: "First" }, { comment: "Second" }]);
        expect(state.analysisHasMore).toBe(false);
        expect(state.analysisLoading).toBe(true);
        expect(state.analysisUnfilteredTotalRows).toBe(3);
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

    it("applies a result payload through one transition", () => {
        applyResultPayload({
            result_id: "result-123",
            filename: "survey.csv",
            analysis_metadata_column_names: ["country"],
            analysis_verbatim_column_names: ["comment"],
            transformed_column_names: ["country", "comment"],
            analysis_column_names: ["comment"],
            available_filters: [{ column_name: "country", options: [] }],
            transformed_preview_rows: [{ country: "UK", comment: "Useful" }],
            analysis_preview_rows: [{ comment: "Useful" }],
            transformed_row_count: 10,
            analysis_row_count: 4,
        });

        expect(state.resultId).toBe("result-123");
        expect(state.selectedAnalysisColumn).toBe("comment");
        expect(state.transformedHasMore).toBe(true);
        expect(state.analysisHasMore).toBe(true);
        expect(state.currentWorkspace).toBe("dashboard");
    });

    it("updates export, preview, and modal sub-states through helpers", () => {
        setAnalysisExportState({ format: "docx", menuOpen: true, running: true });
        setDataExportState({ menuOpen: true, running: true });
        setPreviewState({
            dataset: "community_analysis",
            showOnlyVerbatim: true,
            columnOffset: 3,
            columnSearchTerm: "topic",
        });
        setAnalysisGroupModalLoading(true);
        applyAnalysisGroupDocumentsPayload({
            documents: [{ text: "Useful" }],
            offset: 0,
            has_more: false,
            total_count: 1,
            hit_count: 2,
        }, { reset: true });
        setAnalysisDocumentTranslationLoading("1:Useful", true);
        setAnalysisDocumentTranslation("1:Useful", {
            text: "Useful",
            translated: false,
            warning: "",
        });
        setAnalysisDocumentTranslationLoading("1:Useful", false);
        setAnalysisGroupModalUnavailable("Refresh this analysis.");

        expect(state.analysisExportFormat).toBe("docx");
        expect(state.dataExportRunning).toBe(true);
        expect(state.dataPreviewDataset).toBe("community_analysis");
        expect(state.previewColumnOffset).toBe(3);
        expect(state.analysisGroupModalDocuments).toEqual([]);
        expect(state.analysisGroupModalUnavailableReason).toBe("Refresh this analysis.");
        expect(state.analysisGroupModalHitCount).toBe(2);
        expect(state.analysisGroupModalTranslations["1:Useful"].text).toBe("Useful");
        expect(state.analysisGroupModalTranslationLoading).toEqual({});
    });

    it("syncs cached response metadata and resets stored result state", () => {
        applyResultPayload({
            result_id: "result-123",
            filename: "survey.csv",
            analysis_metadata_column_names: ["country"],
            analysis_verbatim_column_names: ["comment"],
            transformed_column_names: ["country", "comment"],
            analysis_column_names: ["comment"],
            available_filters: [],
            transformed_preview_rows: [],
            analysis_preview_rows: [],
            transformed_row_count: 0,
            analysis_row_count: 0,
        });
        state.analysisMetadataColumns = ["region"];
        const response = syncResultResponseMetadata();

        expect(response.analysis_metadata_column_names).toEqual(["region"]);

        resetStoredResultState();

        expect(state.response).toBeNull();
        expect(state.resultId).toBeNull();
        expect(state.analysisRows).toEqual([]);
    });
});
