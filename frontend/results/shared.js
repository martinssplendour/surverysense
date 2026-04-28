// Public shared facade: expose constants, DOM references, and global results state.
export {
    ANALYSIS_MODE_OPTIONS,
    FULL_DATA_INITIAL_VISIBLE_ROW_TARGET,
    FULL_DATA_ROW_PAGE_SIZE,
    FULL_DATA_VISIBLE_COLUMN_COUNT,
    INITIAL_VISIBLE_ROW_TARGET,
    RESULT_STORAGE_KEY,
    ROW_PAGE_SIZE,
} from "./shared/constants.js";
export { elements } from "./shared/elements.js";
export {
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
} from "./shared/state.js";
