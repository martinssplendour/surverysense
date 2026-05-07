export const RESULT_STORAGE_KEY = "verbatim-app:last-upload-result";
export const RESULT_STORAGE_TTL_MS = 2 * 60 * 60 * 1000;
export const ROW_PAGE_SIZE = 250;
export const INITIAL_VISIBLE_ROW_TARGET = 250;
export const FULL_DATA_ROW_PAGE_SIZE = 50;
export const FULL_DATA_INITIAL_VISIBLE_ROW_TARGET = 50;
export const FULL_DATA_VISIBLE_COLUMN_COUNT = 12;
export const COMMUNITY_SIMILARITY_THRESHOLD_MIN = 0.6;
export const COMMUNITY_SIMILARITY_THRESHOLD_MAX = 1.0;
export const COMMUNITY_SIMILARITY_THRESHOLD_STEP = 0.01;
export const COMMUNITY_SIMILARITY_THRESHOLD_DEFAULT = 0.89;
export const ANALYSIS_MODE_OPTIONS = [
    { key: "community", label: "Community Detection", description: "Groups similar responses into clear groups, so you can see what topics people are talking about most often." },
    { key: "ngrams", label: "N-grams", description: "Highlights the most repeated words and phrases in the text. Pick this when you want the quickest read on repeated language rather than grouped topics." },
];
