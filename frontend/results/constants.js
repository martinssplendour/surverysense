export const RESULT_STORAGE_KEY = "verbatim-app:last-upload-result";
export const ROW_PAGE_SIZE = 250;
export const INITIAL_VISIBLE_ROW_TARGET = 250;
export const FULL_DATA_ROW_PAGE_SIZE = 50;
export const FULL_DATA_INITIAL_VISIBLE_ROW_TARGET = 50;
export const FULL_DATA_VISIBLE_COLUMN_COUNT = 12;
export const ANALYSIS_MODE_OPTIONS = [
    { key: "bertopic", label: "BERTopic", description: "Groups similar responses into topics. Pick this when you want natural topics without presetting the number of groups." },
    { key: "kmeans", label: "K-means", description: "Splits responses into a fixed number of similarity groups. Pick this when you already know roughly how many groups you expect." },
    { key: "hdbscan", label: "HDBSCAN", description: "Finds dense similarity groups and can leave outliers unassigned. Pick this when you want tighter groups and are happy to leave some responses unmatched." },
    { key: "ngrams", label: "N-grams", description: "Highlights the most repeated words and phrases in the text. Pick this when you want the quickest read on repeated language rather than grouped topics." },
];
