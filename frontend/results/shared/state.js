/**
 * Central mutable state for the results page. All sub-modules read from and write to this object directly.
 * Shape summary:
 *   response / resultId        - raw API payload and its server-side ID
 *   analysisVerbatimColumns    - columns eligible for NLP analysis
 *   analysisMetadataColumns    - columns available as filter dimensions
 *   transformed* / analysis* / communityAnalysis* - row sets for full-data, verbatim-only, and community assignment views
 *   activeFilters              - { [columnName]: string[] } applied to row fetches and analysis runs
 *   analysisResult             - last /run-analysis response, or null if not yet run
 *   analysisGroupModal*        - all state for the drilldown modal (mode: "group" | "ngram")
 *   currentWorkspace           - "dashboard" | "data" | "analysis" | "analysis-results"
 */
export const state = {
    response: null,
    resultId: null,
    analysisMetadataColumns: [],
    analysisVerbatimColumns: [],
    transformedColumnNames: [],
    analysisColumnNames: [],
    communityAnalysisColumnNames: [],
    availableFilters: [],
    selectedFilterColumn: "",
    selectedFilterValue: "",
    activeFilters: {},
    showOnlyVerbatim: false,
    dataPreviewDataset: null,
    transformedRows: [],
    analysisRows: [],
    communityAnalysisRows: [],
    transformedTotalRows: 0,
    analysisTotalRows: 0,
    communityAnalysisTotalRows: 0,
    transformedUnfilteredTotalRows: 0,
    analysisUnfilteredTotalRows: 0,
    communityAnalysisUnfilteredTotalRows: 0,
    transformedHasMore: false,
    analysisHasMore: false,
    communityAnalysisHasMore: false,
    transformedLoading: false,
    analysisLoading: false,
    communityAnalysisLoading: false,
    dataExportMenuOpen: false,
    dataExportRunning: false,
    selectedAnalysisColumn: "",
    selectedAnalysisModel: "community",
    communityChartView: "bar",
    analysisResult: null,
    analysisRunning: false,
    analysisExportFormat: "pdf",
    analysisExportMenuOpen: false,
    analysisExportRunning: false,
    analysisGroupModalMode: "group",
    analysisGroupModalGroupId: "",
    analysisGroupModalNgramSize: 0,
    analysisGroupModalTerm: "",
    analysisGroupModalSourceTerm: "",
    analysisGroupModalHitCount: 0,
    analysisGroupModalTotalCount: 0,
    analysisGroupModalBucketLabel: "",
    analysisGroupModalDocuments: [],
    analysisGroupModalTranslations: {},
    analysisGroupModalTranslationLoading: {},
    analysisGroupModalHasMore: false,
    analysisGroupModalOffset: 0,
    analysisGroupModalLoading: false,
    currentWorkspace: "dashboard",
    previewColumnOffset: 0,
    columnSearchTerm: "",
};
