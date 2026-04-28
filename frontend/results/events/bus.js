export const bus = new EventTarget();

/**
 * Dispatches an app-local event with an optional detail payload.
 *
 * @param {string} type Event name.
 * @param {object} [detail] Event payload.
 * @returns {boolean} Whether the event was dispatched without cancellation.
 */
export function emit(type, detail = {}) {
    return bus.dispatchEvent(createCustomEvent(type, detail));
}

/**
 * Registers an app-local event listener.
 *
 * @param {string} type Event name.
 * @param {(detail: object, event: Event) => void} handler Event handler.
 * @returns {() => void} Function that removes the listener.
 */
export function on(type, handler) {
    const listener = (event) => {
        handler("detail" in event ? event.detail : {}, event);
    };
    bus.addEventListener(type, listener);
    return () => {
        bus.removeEventListener(type, listener);
    };
}

function createCustomEvent(type, detail) {
    if (typeof CustomEvent === "function") {
        return new CustomEvent(type, { detail });
    }

    const event = new Event(type);
    event.detail = detail;
    return event;
}
