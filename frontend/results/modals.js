// Stable facade for analysis response drilldown modal modules.
export {
    closeAnalysisGroupModal,
    openAnalysisGroupModalByIndex,
    openAnalysisNgramModal,
} from "./analysisGroupModal/controller.js";
export {
    loadAnalysisGroupDocuments,
    loadAnalysisNgramDocuments,
    translateAnalysisDocument,
} from "./analysisGroupModal/api.js";
