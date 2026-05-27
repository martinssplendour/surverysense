import { RESULT_STORAGE_KEY, RESULT_STORAGE_TTL_MS, state, syncResultResponseMetadata } from "../shared.js";


export function clearStoredPayload() {
    sessionStorage.removeItem(RESULT_STORAGE_KEY);
}


export function persistCurrentResultPayload() {
    if (!state.response) {
        return;
    }

    const response = syncResultResponseMetadata();
    try {
        sessionStorage.setItem(RESULT_STORAGE_KEY, JSON.stringify(wrapStoredPayload(response)));
    } catch (error) {
        console.warn(
            "[SurveySense] Failed to update the cached processed result; the current screen still works, but a later restore may be out of date.",
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
        const payload = unwrapStoredPayload(parsed);
        if (!payload) {
            clearStoredPayload();
            return null;
        }
        return payload;
    } catch {
        clearStoredPayload();
        return null;
    }
}


function wrapStoredPayload(payload) {
    return {
        payload,
        expires_at: Date.now() + RESULT_STORAGE_TTL_MS,
    };
}


function unwrapStoredPayload(value) {
    if (isValidStoredPayload(value)) {
        return value;
    }
    if (!value || typeof value !== "object") {
        return null;
    }
    const expiresAt = Number(value.expires_at);
    if (!Number.isFinite(expiresAt) || expiresAt <= Date.now()) {
        return null;
    }
    return isValidStoredPayload(value.payload) ? value.payload : null;
}


function isValidStoredPayload(payload) {
    return Boolean(payload) && Array.isArray(payload.transformed_column_names);
}
