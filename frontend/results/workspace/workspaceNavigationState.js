export function isPageReload() {
    if (typeof window === "undefined" || typeof performance === "undefined") {
        return false;
    }

    const navigationEntries = typeof performance.getEntriesByType === "function"
        ? performance.getEntriesByType("navigation")
        : [];
    const firstEntry = Array.isArray(navigationEntries) ? navigationEntries[0] : null;
    if (firstEntry && typeof firstEntry === "object" && "type" in firstEntry) {
        return firstEntry.type === "reload";
    }

    const legacyNavigation = performance.navigation;
    return Boolean(legacyNavigation && legacyNavigation.type === 1);
}


export function isUploadHandoffNavigation() {
    if (typeof window === "undefined") {
        return false;
    }
    const params = new URLSearchParams(window.location.search);
    return params.get("handoff") === "1";
}


export function clearUploadHandoffQuery() {
    if (typeof window === "undefined" || typeof history.replaceState !== "function") {
        return;
    }
    const params = new URLSearchParams(window.location.search);
    if (params.get("handoff") !== "1") {
        return;
    }
    params.delete("handoff");
    const query = params.toString();
    const nextUrl = `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash || ""}`;
    history.replaceState(null, "", nextUrl);
}
