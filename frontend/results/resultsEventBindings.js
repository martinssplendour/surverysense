import { bindAnalysisEvents } from "./events/analysisEvents.js";
import { bindDataExportEvents } from "./events/dataExportEvents.js";
import { bindFilterTableEvents } from "./events/filterTableEvents.js";
import { bindModalEvents } from "./events/modalEvents.js";
import { bindNavigationEvents } from "./events/navigationEvents.js";

export function bindResultsEvents() {
    bindNavigationEvents();
    bindDataExportEvents();
    bindAnalysisEvents();
    bindModalEvents();
    bindFilterTableEvents();
}
