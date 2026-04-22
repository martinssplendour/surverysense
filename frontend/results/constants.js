export const RESULT_STORAGE_KEY = "verbatim-app:last-upload-result";
export const ROW_PAGE_SIZE = 250;
export const INITIAL_VISIBLE_ROW_TARGET = 250;
export const FULL_DATA_ROW_PAGE_SIZE = 50;
export const FULL_DATA_INITIAL_VISIBLE_ROW_TARGET = 50;
export const FULL_DATA_VISIBLE_COLUMN_COUNT = 12;
export const ANALYSIS_MODE_OPTIONS = [
    { key: "community", label: "Community Detection", description: "Builds a similarity network from responses and finds natural communities." },
    { key: "ngrams", label: "N-grams", description: "Highlights the most repeated words and phrases in the text. Pick this when you want the quickest read on repeated language rather than grouped topics." },
];
