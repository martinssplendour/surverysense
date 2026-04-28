// Public drilldown modal facade: expose analysis response modal APIs from one stable path.
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
