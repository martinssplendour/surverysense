// Coordinates analysis report export and preview actions.
import { state } from "../../shared.js";
import { requestAnalysisReportBlob } from "./request.js";
import { normalizeAnalysisExportFormat } from "./format.js";
import {
    openPreparingPreviewWindow,
    writeHtmlReportPreviewPage,
    writePreviewErrorPage,
} from "./previewWindow.js";


const callbacks = {
    clearAnalysisMessage: () => {},
    handleMissingResultState: () => {},
    parseJson: async () => ({}),
    renderAnalysisExportControls: () => {},
    renderAnalysisMessage: () => {},
};


export function configureChartExport(nextCallbacks) {
    Object.assign(callbacks, nextCallbacks);
}


export async function downloadAnalysisReport() {
    if (!state.resultId || !state.analysisResult?.ok || state.analysisExportRunning) {
        return;
    }

    state.analysisExportFormat = normalizeAnalysisExportFormat(state.analysisExportFormat);
    state.analysisExportMenuOpen = false;
    state.analysisExportRunning = true;
    callbacks.renderAnalysisExportControls();

    try {
        const artifact = await requestAnalysisReportBlob({ format: state.analysisExportFormat || "pdf", callbacks });
        if (!artifact) {
            return;
        }
        const objectUrl = URL.createObjectURL(artifact.blob);
        const anchor = document.createElement("a");
        anchor.href = objectUrl;
        anchor.download = artifact.filename;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(objectUrl);
        callbacks.clearAnalysisMessage();
    } catch (error) {
        const message = error instanceof Error ? error.message : "Unable to export the report.";
        callbacks.renderAnalysisMessage("error", message);
    } finally {
        state.analysisExportRunning = false;
        callbacks.renderAnalysisExportControls();
    }
}


export async function previewAnalysisReport() {
    if (!state.resultId || !state.analysisResult?.ok || state.analysisExportRunning) {
        return;
    }

    state.analysisExportFormat = normalizeAnalysisExportFormat(state.analysisExportFormat);
    const previewWindow = openPreparingPreviewWindow();
    if (!previewWindow) {
        callbacks.renderAnalysisMessage("error", "Unable to open the preview tab. Allow pop-ups for this site and try again.");
        return;
    }

    state.analysisExportMenuOpen = false;
    state.analysisExportRunning = true;
    callbacks.renderAnalysisExportControls();

    try {
        const artifact = await requestAnalysisReportBlob({ format: state.analysisExportFormat, callbacks });
        if (!artifact) {
            previewWindow.close();
            return;
        }
        const objectUrl = URL.createObjectURL(artifact.blob);
        writeHtmlReportPreviewPage(previewWindow, {
            objectUrl,
            filename: artifact.filename,
            format: artifact.format,
            exportPayload: artifact.exportPayload,
        });
        callbacks.clearAnalysisMessage();
    } catch (error) {
        const message = error instanceof Error ? error.message : "Unable to preview the report.";
        writePreviewErrorPage(previewWindow, message);
        callbacks.renderAnalysisMessage("error", message);
    } finally {
        state.analysisExportRunning = false;
        callbacks.renderAnalysisExportControls();
    }
}
