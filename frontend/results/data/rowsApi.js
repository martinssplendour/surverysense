import { RESULT_STORAGE_KEY, state } from "../shared.js";


export async function fetchRowsPage(dataset, offset, limit, { hasActiveFilters, handleMissingResultState }) {
    const query = new URLSearchParams({
        dataset,
        offset: `${offset}`,
        limit: `${limit}`,
    });
    if (hasActiveFilters()) {
        query.set("filters", JSON.stringify(state.activeFilters));
    }

    const response = await fetch(`/result-rows/${encodeURIComponent(state.resultId)}?${query.toString()}`);
    if (response.status === 401) {
        sessionStorage.removeItem(RESULT_STORAGE_KEY);
        window.location.assign("/login");
        throw new Error("Session expired.");
    }
    if (response.status === 404) {
        const payload = await parseJson(response);
        handleMissingResultState(payload.detail || "The processed result is no longer available.");
        throw new Error("The processed result is no longer available.");
    }

    const payload = await parseJson(response);
    if (!response.ok) {
        throw new Error(payload.detail || "Unable to load rows.");
    }
    return payload;
}


export async function parseJson(response) {
    try {
        return await response.json();
    } catch {
        return {};
    }
}
