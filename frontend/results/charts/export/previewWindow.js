// Owns the browser preview window lifecycle for generated report previews.
import { displayAnalysisExportFormat } from "./format.js";
import { buildReportPreviewModel } from "./previewModel.js";
import {
    buildDocumentPreviewMarkup,
    buildSlidesPreviewMarkup,
    escapePreviewAttribute,
    escapePreviewHtml,
    toSafeScriptString,
} from "./previewMarkup.js";


export function openPreparingPreviewWindow() {
    const previewWindow = window.open("", "_blank");
    if (!previewWindow) {
        return null;
    }
    previewWindow.document.open();
    previewWindow.document.write(`<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Preparing Report Preview</title>
    <style>
        body { margin: 0; min-height: 100vh; display: grid; place-items: center; font-family: "Segoe UI", Aptos, sans-serif; background: #ffffff; color: #000000; }
        .card { padding: 28px 32px; border-radius: 12px; background: #fff; border: 1px solid #e3e8f1; box-shadow: 0 18px 46px rgba(17,24,39,.08); }
        h1 { margin: 0 0 8px; color: #2477F8; font-size: 1.1rem; }
        p { margin: 0; color: #000000; }
    </style>
</head>
<body>
    <main class="card">
        <h1>Preparing report preview...</h1>
        <p>The selected report file will open here when it is ready.</p>
    </main>
</body>
</html>`);
    previewWindow.document.close();
    return previewWindow;
}


export function writeHtmlReportPreviewPage(previewWindow, { objectUrl, filename, format, exportPayload }) {
    const previewModel = buildReportPreviewModel(exportPayload);
    const bodyMarkup = format === "pptx"
        ? buildSlidesPreviewMarkup(previewModel)
        : buildDocumentPreviewMarkup(previewModel, { format });
    const formatLabel = displayAnalysisExportFormat(format);
    previewWindow.document.open();
    previewWindow.document.write(`<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>${escapePreviewHtml(formatLabel)} Report Preview</title>
    <style>
        :root { color-scheme: light; --green: #2477F8; --text: #000000; --muted: #000000; --paper: #ffffff; --line: #e3e8f1; --soft: #ffffff; }
        * { box-sizing: border-box; }
        body { margin: 0; min-height: 100vh; display: grid; grid-template-rows: auto 1fr; font-family: Aptos, "Segoe UI", sans-serif; background: #ffffff; color: var(--text); }
        .preview-toolbar { position: sticky; top: 0; z-index: 10; display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 12px 18px; background: rgba(255,255,255,.98); border-bottom: 1px solid var(--line); box-shadow: 0 8px 24px rgba(17,24,39,.06); }
        .preview-toolbar h1 { margin: 0; font-size: 1rem; letter-spacing: -.01em; }
        .preview-toolbar p { margin: 3px 0 0; color: var(--text); font-size: .84rem; }
        .preview-toolbar a { display: inline-flex; align-items: center; justify-content: center; min-height: 38px; padding: 9px 16px; border-radius: 999px; background: var(--green); color: #fff; font-weight: 800; text-decoration: none; white-space: nowrap; }
        .preview-stage { display: grid; justify-items: center; gap: 22px; padding: 28px; overflow: auto; }
        .report-page { width: 794px; min-height: 1123px; padding: 56px; background: var(--paper); box-shadow: 0 18px 46px rgba(17,24,39,.08); border: 1px solid var(--line); }
        .doc-page { width: 816px; min-height: 1056px; padding: 58px 68px; }
        .report-title { margin: 0 0 6px; font-family: "Aptos Display", Aptos, sans-serif; font-size: 29px; line-height: 1.18; color: var(--green); letter-spacing: -.02em; }
        .report-subtitle { margin: 0 0 18px; color: var(--green); font-size: 13px; line-height: 1.45; }
        .pdf-title { font-family: Helvetica, Arial, sans-serif; font-size: 29px; }
        .pdf-page { font-family: Helvetica, Arial, sans-serif; }
        .section-title { margin: 22px 0 10px; color: var(--green); font-size: 18px; line-height: 1.25; }
        .summary-item { margin: 0 0 10px; }
        .summary-item h3 { margin: 0 0 4px; font-size: 14px; color: var(--green); }
        .summary-item p, .example-list li, .summary-line { margin: 0; font-size: 13px; line-height: 1.45; color: var(--text); }
        .example-list { margin: 4px 0 14px 20px; padding: 0; }
        .chart-block { margin: 16px 0 24px; text-align: center; }
        .chart-block h2 { margin: 0 0 6px; font-size: 16px; color: var(--green); }
        .chart-block p { margin: 0 0 10px; color: var(--text); font-size: 12px; font-style: italic; line-height: 1.35; }
        .chart-block img { max-width: 100%; max-height: 620px; object-fit: contain; }
        .slide { width: 960px; height: 540px; padding: 44px 72px; background: #ffffff; box-shadow: 0 18px 46px rgba(17,24,39,.08); border: 1px solid var(--line); position: relative; overflow: hidden; }
        .slide-title { margin: 0 0 18px; color: var(--green); font-size: 28px; line-height: 1.12; letter-spacing: -.03em; }
        .slide-subtitle { max-width: 620px; margin: 0; color: var(--green); font-size: 14px; line-height: 1.45; }
        .slide-cover { display: flex; flex-direction: column; justify-content: center; }
        .slide-cover .slide-title { max-width: 640px; font-size: 35px; }
        .slide-chart img { max-width: 821px; max-height: 456px; object-fit: contain; display: block; margin-top: 12px; }
        .slide-caption { color: var(--text); font-size: 13px; margin: -6px 0 12px; }
        .slide-summary-grid { display: grid; gap: 16px; max-width: 680px; }
        .slide-summary-item h3 { margin: 0 0 5px; color: var(--green); font-size: 20px; line-height: 1.15; }
        .slide-summary-item p, .slide-example-list li { margin: 0; color: var(--text); font-size: 15px; line-height: 1.35; }
        .slide-example-list { margin: 6px 0 22px 20px; padding: 0; max-width: 690px; }
        @media (max-width: 860px) { .preview-stage { align-items: start; justify-items: start; } }
    </style>
</head>
<body>
    <header class="preview-toolbar">
        <div>
            <h1>${escapePreviewHtml(formatLabel)} Report Preview</h1>
            <p>This HTML/CSS preview mirrors the selected export layout. Use Download for the generated file.</p>
        </div>
        <a href="${escapePreviewAttribute(objectUrl)}" download="${escapePreviewAttribute(filename)}">Download ${escapePreviewHtml(formatLabel)}</a>
    </header>
    <main class="preview-stage">
        ${bodyMarkup}
    </main>
    <script>
        const reportUrl = ${toSafeScriptString(objectUrl)};
        window.addEventListener("beforeunload", () => URL.revokeObjectURL(reportUrl));
    </script>
</body>
</html>`);
    previewWindow.document.close();
}


export function writePreviewErrorPage(previewWindow, message) {
    previewWindow.document.open();
    previewWindow.document.write(`<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Report Preview Failed</title>
    <style>
        body { margin: 0; min-height: 100vh; display: grid; place-items: center; font-family: "Segoe UI", Aptos, sans-serif; background: #ffffff; color: #000000; }
        .card { max-width: 680px; padding: 28px 32px; border-radius: 12px; background: #fff; border: 1px solid #e3e8f1; box-shadow: 0 18px 46px rgba(17,24,39,.08); }
        h1 { margin: 0 0 8px; color: #2477F8; font-size: 1.1rem; }
        p { margin: 0; color: #000000; line-height: 1.5; }
    </style>
</head>
<body>
    <main class="card">
        <h1>Preview could not be prepared</h1>
        <p id="preview-error"></p>
    </main>
    <script>
        document.getElementById("preview-error").textContent = ${toSafeScriptString(message)};
    </script>
</body>
</html>`);
    previewWindow.document.close();
}
