// Builds the export payload and requests a generated report artifact from the backend.
import { RESULT_STORAGE_KEY, elements, state } from "../../shared.js";
import { parseDownloadFilename } from "../../shared/utils.js";
import {
    buildAnalysisExportFileStem,
    buildAnalysisExportFilters,
    buildAnalysisExportTitle,
} from "../exportMetadata.js";
import { normalizeAnalysisExportFormat } from "./format.js";
import { captureRenderedAnalysisCharts } from "./generatedCharts.js";


export async function requestAnalysisReportBlob({ format, callbacks }) {
    const normalizedFormat = normalizeAnalysisExportFormat(format);
    const charts = await captureRenderedAnalysisCharts();
    const exportPayload = {
        format: normalizedFormat,
        report_title: buildAnalysisExportTitle(),
        source_filename: state.response?.filename || "",
        subtitle: elements.analysisResultsSubtitle?.textContent?.trim() || "",
        active_filters: buildAnalysisExportFilters(),
        charts,
        analysis_result: buildAnalysisExportResultPayload(),
    };
    const response = await fetch(`/analysis-export/${encodeURIComponent(state.resultId)}`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(exportPayload),
    });
    if (response.status === 401) {
        sessionStorage.removeItem(RESULT_STORAGE_KEY);
        window.location.assign("/login");
        return null;
    }
    if (response.status === 403 || response.status === 404) {
        const payload = await callbacks.parseJson(response);
        callbacks.handleMissingResultState(payload.detail || "The processed result is no longer available.");
        return null;
    }
    if (!response.ok) {
        const payload = await callbacks.parseJson(response);
        throw new Error(payload.detail || "Unable to export the report.");
    }

    const blob = await response.blob();
    const filename = parseDownloadFilename(response.headers.get("Content-Disposition"))
        || `${buildAnalysisExportFileStem()}.${normalizedFormat}`;
    return {
        blob,
        filename,
        format: normalizedFormat,
        exportPayload,
    };
}

export function buildAnalysisExportResultPayload() {
    const result = state.analysisResult || {};
    const textColumnName = String(result.text_column_name || "").trim() || state.selectedAnalysisColumn || "";
    return {
        ...result,
        text_column_name: textColumnName,
    };
}
