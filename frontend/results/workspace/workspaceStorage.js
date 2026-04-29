import { RESULT_STORAGE_KEY, state, syncResultResponseMetadata } from "../shared.js";


export function clearStoredPayload() {
    sessionStorage.removeItem(RESULT_STORAGE_KEY);
}


export function persistCurrentResultPayload() {
    if (!state.response) {
        return;
    }

    const response = syncResultResponseMetadata();
    try {
        sessionStorage.setItem(RESULT_STORAGE_KEY, JSON.stringify(response));
    } catch (error) {
        console.warn(
            "[Verbatim App] Failed to update the cached processed result; the current screen still works, but a later restore may be out of date.",
            error,
        );
    }
}


export function readStoredPayload() {
    const raw = sessionStorage.getItem(RESULT_STORAGE_KEY);
    if (!raw) {
        return null;
    }

    try {
        const parsed = JSON.parse(raw);
        if (!isValidStoredPayload(parsed)) {
            return null;
        }
        return parsed;
    } catch {
        return null;
    }
}


function isValidStoredPayload(payload) {
    return Boolean(payload) && Array.isArray(payload.transformed_column_names);
}
