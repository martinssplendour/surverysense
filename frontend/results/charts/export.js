// Exports analysis results as PDF, DOCX, or PPTX by capturing Plotly chart images and posting them to the backend.
import { RESULT_STORAGE_KEY, elements, state } from "../shared.js";
import {
    displayColumnLabel,
    parseDownloadFilename,
} from "../shared/utils.js";
import { captureAnalysisChartImage, getPlotly } from "./exportFigure.js";
import {
    buildAnalysisChartDefinitions,
    buildAnalysisExportFileStem,
    buildAnalysisExportFilters,
    buildAnalysisExportTitle,
    resolveAnalysisExportDimensions,
} from "./exportMetadata.js";


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


export function normalizeAnalysisExportFormat(value) {
    return value === "docx" || value === "pptx" || value === "pdf"
        ? value
        : "pdf";
}


export function displayAnalysisExportFormat(value) {
    switch (normalizeAnalysisExportFormat(value)) {
    case "docx":
        return "Doc";
    case "pptx":
        return "Slides";
    default:
        return "PDF";
    }
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
        const artifact = await requestAnalysisReportBlob({ format: state.analysisExportFormat || "pdf" });
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
        const artifact = await requestAnalysisReportBlob({ format: state.analysisExportFormat });
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


async function requestAnalysisReportBlob({ format }) {
    const normalizedFormat = normalizeAnalysisExportFormat(format);
    const charts = await captureRenderedAnalysisCharts();
    const exportPayload = {
        format: normalizedFormat,
        report_title: buildAnalysisExportTitle(),
        source_filename: state.response?.filename || "",
        subtitle: elements.analysisResultsSubtitle?.textContent?.trim() || "",
        active_filters: buildAnalysisExportFilters(),
        charts,
        analysis_result: state.analysisResult,
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
    if (response.status === 404) {
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


function openPreparingPreviewWindow() {
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
        body { margin: 0; min-height: 100vh; display: grid; place-items: center; font-family: "Segoe UI", Aptos, sans-serif; background: #f7f2ea; color: #2f2b26; }
        .card { padding: 28px 32px; border-radius: 20px; background: #fff; border: 1px solid rgba(89,68,42,.12); box-shadow: 0 24px 70px rgba(58,44,27,.14); }
        h1 { margin: 0 0 8px; font-size: 1.1rem; }
        p { margin: 0; color: #6d6359; }
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


function writeHtmlReportPreviewPage(previewWindow, { objectUrl, filename, format, exportPayload }) {
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
        :root { color-scheme: light; --green: #2477F8; --text: #3d352d; --muted: #5e574f; --paper: #ffffff; --line: #d8cdbf; --soft: #f7f2ea; }
        * { box-sizing: border-box; }
        body { margin: 0; min-height: 100vh; display: grid; grid-template-rows: auto 1fr; font-family: Aptos, "Segoe UI", sans-serif; background: #ece4d8; color: var(--text); }
        .preview-toolbar { position: sticky; top: 0; z-index: 10; display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 12px 18px; background: rgba(255,255,255,.96); border-bottom: 1px solid rgba(89,68,42,.14); box-shadow: 0 10px 30px rgba(58,44,27,.08); }
        .preview-toolbar h1 { margin: 0; font-size: 1rem; letter-spacing: -.01em; }
        .preview-toolbar p { margin: 3px 0 0; color: #6d6359; font-size: .84rem; }
        .preview-toolbar a { display: inline-flex; align-items: center; justify-content: center; min-height: 38px; padding: 9px 16px; border-radius: 999px; background: var(--green); color: #fff; font-weight: 800; text-decoration: none; white-space: nowrap; }
        .preview-stage { display: grid; justify-items: center; gap: 22px; padding: 28px; overflow: auto; }
        .report-page { width: 794px; min-height: 1123px; padding: 56px; background: var(--paper); box-shadow: 0 18px 56px rgba(58,44,27,.18); border: 1px solid rgba(89,68,42,.1); }
        .doc-page { width: 816px; min-height: 1056px; padding: 58px 68px; }
        .report-title { margin: 0 0 6px; font-family: "Aptos Display", Aptos, sans-serif; font-size: 29px; line-height: 1.18; color: var(--green); letter-spacing: -.02em; }
        .report-subtitle { margin: 0 0 18px; color: var(--muted); font-size: 13px; line-height: 1.45; }
        .pdf-title { font-family: Helvetica, Arial, sans-serif; font-size: 29px; }
        .pdf-page { font-family: Helvetica, Arial, sans-serif; }
        .section-title { margin: 22px 0 10px; color: var(--green); font-size: 18px; line-height: 1.25; }
        .summary-item { margin: 0 0 10px; }
        .summary-item h3 { margin: 0 0 4px; font-size: 14px; color: var(--text); }
        .summary-item p, .example-list li, .summary-line { margin: 0; font-size: 13px; line-height: 1.45; color: var(--text); }
        .example-list { margin: 4px 0 14px 20px; padding: 0; }
        .chart-block { margin: 16px 0 24px; text-align: center; }
        .chart-block h2 { margin: 0 0 6px; font-size: 16px; color: var(--green); }
        .chart-block p { margin: 0 0 10px; color: #625b52; font-size: 12px; font-style: italic; line-height: 1.35; }
        .chart-block img { max-width: 100%; max-height: 620px; object-fit: contain; }
        .slide { width: 960px; height: 540px; padding: 44px 72px; background: #f7f2ea; box-shadow: 0 18px 56px rgba(58,44,27,.18); border: 1px solid rgba(89,68,42,.12); position: relative; overflow: hidden; }
        .slide-title { margin: 0 0 18px; color: #2f2b26; font-size: 28px; line-height: 1.12; letter-spacing: -.03em; }
        .slide-subtitle { max-width: 620px; margin: 0; color: #6d6359; font-size: 14px; line-height: 1.45; }
        .slide-cover { display: flex; flex-direction: column; justify-content: center; }
        .slide-cover .slide-title { max-width: 640px; font-size: 35px; }
        .slide-chart img { max-width: 912px; max-height: 507px; object-fit: contain; display: block; margin-top: 12px; }
        .slide-caption { color: #6d6359; font-size: 13px; margin: -6px 0 12px; }
        .slide-summary-grid { display: grid; gap: 16px; max-width: 680px; }
        .slide-summary-item h3 { margin: 0 0 5px; font-size: 20px; line-height: 1.15; }
        .slide-summary-item p, .slide-example-list li { margin: 0; color: #6d6359; font-size: 15px; line-height: 1.35; }
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


function buildReportPreviewModel(exportPayload) {
    const result = exportPayload.analysis_result || {};
    const groups = Array.isArray(result.groups) ? [...result.groups] : [];
    const groupSections = groups
        .sort((left, right) => Number(right.count || 0) - Number(left.count || 0) || String(left.label || "").localeCompare(String(right.label || "")))
        .slice(0, 8)
        .map((group) => {
            const terms = Array.isArray(group.terms) && group.terms.length
                ? group.terms.slice(0, 4).join(", ")
                : "no top terms available";
            const sharePercent = Math.round(Number(group.share || 0) * 100);
            const examples = Array.isArray(group.examples)
                ? group.examples.slice(0, 3).map((example) => truncatePreviewText(example.text || "", 240)).filter(Boolean)
                : [];
            return {
                label: group.label || "Unlabelled group",
                summary: `${Number(group.count || 0)} responses (${sharePercent}%). Top terms: ${terms}.`,
                examples,
            };
        });

    return {
        title: "Verbatim Analysis Report",
        subtitle: buildPreviewSubtitle(exportPayload),
        charts: Array.isArray(exportPayload.charts) ? exportPayload.charts : [],
        summaryHeading: buildPreviewSummaryHeading(result),
        summaryLines: buildPreviewSummaryLines(result, groupSections),
        groupSections,
        representativeHeading: "Representative documents (groups and top 3 responses)",
        representativeSections: groupSections
            .filter((section) => section.examples.length)
            .map((section) => [section.label, section.examples]),
    };
}


function buildDocumentPreviewMarkup(model, { format }) {
    const pageClass = format === "docx" ? "report-page doc-page" : "report-page pdf-page";
    const titleClass = format === "docx" ? "report-title" : "report-title pdf-title";
    const chartMarkup = model.charts.length
        ? `<section class="${pageClass}">
            <h1 class="${titleClass}">${escapePreviewHtml(model.title)}</h1>
            <p class="report-subtitle">${escapePreviewHtml(model.subtitle)}</p>
            ${model.charts.map(buildDocumentChartMarkup).join("")}
        </section>`
        : "";
    const summaryPage = `<section class="${pageClass}">
        ${model.charts.length ? "" : `<h1 class="${titleClass}">${escapePreviewHtml(model.title)}</h1><p class="report-subtitle">${escapePreviewHtml(model.subtitle)}</p>`}
        <h2 class="section-title">${escapePreviewHtml(model.summaryHeading)}</h2>
        ${model.groupSections.length
        ? model.groupSections.map(buildSummaryItemMarkup).join("")
        : model.summaryLines.map((line) => `<p class="summary-line">- ${escapePreviewHtml(line)}</p>`).join("")}
        ${model.representativeSections.length ? `
            <h2 class="section-title">${escapePreviewHtml(model.representativeHeading)}</h2>
            ${model.representativeSections.map(([label, examples]) => `
                <div class="summary-item">
                    <h3>${escapePreviewHtml(label)}</h3>
                    <ol class="example-list">
                        ${examples.map((example) => `<li>${escapePreviewHtml(example)}</li>`).join("")}
                    </ol>
                </div>
            `).join("")}
        ` : ""}
    </section>`;
    return `${chartMarkup}${summaryPage}`;
}


function buildSlidesPreviewMarkup(model) {
    const slides = [
        `<section class="slide slide-cover">
            <h1 class="slide-title">${escapePreviewHtml(model.title)}</h1>
            <p class="slide-subtitle">${escapePreviewHtml(model.subtitle)}</p>
        </section>`,
        ...model.charts.map((chart) => `
            <section class="slide slide-chart">
                <h2 class="slide-title">${escapePreviewHtml(chart.title || "Chart")}</h2>
                ${chart.caption ? `<p class="slide-caption">${escapePreviewHtml(chart.caption)}</p>` : ""}
                ${chart.image_data_url ? `<img src="${escapePreviewAttribute(chart.image_data_url)}" alt="${escapePreviewAttribute(chart.title || "Chart")}">` : ""}
            </section>
        `),
    ];

    if (model.groupSections.length) {
        for (let index = 0; index < model.groupSections.length; index += 4) {
            const chunk = model.groupSections.slice(index, index + 4);
            slides.push(`
                <section class="slide">
                    <h2 class="slide-title">${escapePreviewHtml(index ? `${model.summaryHeading} (continued)` : model.summaryHeading)}</h2>
                    <div class="slide-summary-grid">
                        ${chunk.map((section) => `
                            <div class="slide-summary-item">
                                <h3>${escapePreviewHtml(section.label)}</h3>
                                <p>${escapePreviewHtml(section.summary)}</p>
                            </div>
                        `).join("")}
                    </div>
                </section>
            `);
        }
    } else {
        slides.push(`
            <section class="slide">
                <h2 class="slide-title">${escapePreviewHtml(model.summaryHeading)}</h2>
                <div class="slide-summary-grid">
                    ${model.summaryLines.slice(0, 8).map((line) => `<p>${escapePreviewHtml(line)}</p>`).join("")}
                </div>
            </section>
        `);
    }

    for (let index = 0; index < model.representativeSections.length; index += 2) {
        const chunk = model.representativeSections.slice(index, index + 2);
        slides.push(`
            <section class="slide">
                <h2 class="slide-title">${escapePreviewHtml(model.representativeHeading)}</h2>
                ${chunk.map(([label, examples]) => `
                    <div class="slide-summary-item">
                        <h3>${escapePreviewHtml(label)}</h3>
                        <ol class="slide-example-list">
                            ${examples.map((example) => `<li>${escapePreviewHtml(example)}</li>`).join("")}
                        </ol>
                    </div>
                `).join("")}
            </section>
        `);
    }
    return slides.join("");
}


function buildDocumentChartMarkup(chart) {
    return `
        <section class="chart-block">
            <h2>${escapePreviewHtml(chart.title || "Chart")}</h2>
            ${chart.caption ? `<p>${escapePreviewHtml(chart.caption)}</p>` : ""}
            ${chart.image_data_url ? `<img src="${escapePreviewAttribute(chart.image_data_url)}" alt="${escapePreviewAttribute(chart.title || "Chart")}">` : ""}
        </section>
    `;
}


function buildSummaryItemMarkup(section) {
    return `
        <div class="summary-item">
            <h3>${escapePreviewHtml(section.label)}</h3>
            <p>${escapePreviewHtml(section.summary)}</p>
        </div>
    `;
}


function buildPreviewSubtitle(exportPayload) {
    const result = exportPayload.analysis_result || {};
    const parts = [displayColumnLabel(result.text_column_name || "")];
    const filtersText = Array.isArray(exportPayload.active_filters)
        ? exportPayload.active_filters
            .filter((item) => Array.isArray(item.values) && item.values.length)
            .map((item) => `${item.display_name || item.column_name}: ${item.values.join(", ")}`)
            .join(" | ")
        : "";
    if (filtersText) {
        parts.push(filtersText);
    }
    parts.push(`${Number(result.filtered_row_count || 0)} rows`);
    return parts.filter(Boolean).join(" | ");
}


function buildPreviewSummaryHeading(result) {
    if (Array.isArray(result.ngram_buckets) && result.ngram_buckets.length) {
        return "Phrase summaries";
    }
    if (result.model_key === "community") {
        return "Community summaries";
    }
    return "Topic summaries";
}


function buildPreviewSummaryLines(result, groupSections) {
    if (Array.isArray(result.ngram_buckets) && result.ngram_buckets.length) {
        const findings = result.ngram_buckets.map((bucket) => {
            const items = Array.isArray(bucket.items) ? bucket.items.slice(0, 5) : [];
            const terms = items.map((item) => `${item.term} (${item.document_count} responses)`).join(", ");
            return terms ? `${bucket.label}: ${terms}` : "";
        }).filter(Boolean);
        return findings.length ? findings : ["No phrase-level findings were available for export."];
    }
    if (groupSections.length) {
        return groupSections.map((section) => `${section.label}: ${section.summary}`);
    }
    return ["The selected analysis completed without exportable topic findings."];
}


function writePreviewErrorPage(previewWindow, message) {
    previewWindow.document.open();
    previewWindow.document.write(`<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Report Preview Failed</title>
    <style>
        body { margin: 0; min-height: 100vh; display: grid; place-items: center; font-family: "Segoe UI", Aptos, sans-serif; background: #f7f2ea; color: #2f2b26; }
        .card { max-width: 680px; padding: 28px 32px; border-radius: 20px; background: #fff; border: 1px solid rgba(153,62,51,.22); box-shadow: 0 24px 70px rgba(58,44,27,.14); }
        h1 { margin: 0 0 8px; font-size: 1.1rem; }
        p { margin: 0; color: #9b463e; line-height: 1.5; }
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


function toSafeScriptString(value) {
    return JSON.stringify(String(value || "")).replace(/</g, "\\u003c");
}


function escapePreviewHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}


function escapePreviewAttribute(value) {
    return escapePreviewHtml(value);
}


function truncatePreviewText(value, limit) {
    const normalized = String(value || "").replace(/\s+/g, " ").trim();
    if (normalized.length <= limit) {
        return normalized;
    }
    return `${normalized.slice(0, Math.max(0, limit - 3)).trim()}...`;
}


async function captureRenderedAnalysisCharts() {
    const plotly = getPlotly();
    if (!plotly || typeof plotly.toImage !== "function" || !(elements.analysisChart instanceof HTMLElement)) {
        return [];
    }

    if (Array.isArray(state.analysisResult?.groups) && state.analysisResult.groups.length) {
        const generatedGroupChart = await captureGeneratedGroupBarChart(plotly);
        return generatedGroupChart ? [generatedGroupChart] : [];
    }

    const plotSurfaces = Array.from(elements.analysisChart.querySelectorAll(".analysis-plot-surface"));
    if (!plotSurfaces.length) {
        return [];
    }

    const chartDefinitions = buildAnalysisChartDefinitions(plotSurfaces.length);
    const images = await Promise.all(
        plotSurfaces.map(async (plotSurface, index) => {
            if (!(plotSurface instanceof HTMLElement)) {
                return null;
            }
            const rect = plotSurface.getBoundingClientRect();
            try {
                const definition = chartDefinitions[index] || chartDefinitions[0] || {
                    title: `Chart ${index + 1}`,
                    caption: "",
                };
                const { width, height } = resolveAnalysisExportDimensions({
                    definition,
                    fallbackWidth: Math.max(1200, Math.round(rect.width * 2) || 1200),
                    fallbackHeight: Math.max(720, Math.round(rect.height * 2) || 720),
                });
                const imageDataUrl = await captureAnalysisChartImage(plotly, plotSurface, {
                    width,
                    height,
                    definition,
                });
                return {
                    title: definition.title,
                    caption: definition.caption,
                    image_data_url: imageDataUrl,
                };
            } catch (error) {
                console.warn(
                    `[Verbatim App] Failed to capture export image for chart ${index + 1}; the report will skip that chart.`,
                    error,
                );
                return null;
            }
        }),
    );

    return images.filter(Boolean);
}


async function captureGeneratedGroupBarChart(plotly) {
    const groups = Array.isArray(state.analysisResult?.groups)
        ? [...state.analysisResult.groups]
            .sort((left, right) => Number(right.count || 0) - Number(left.count || 0))
            .slice(0, 12)
        : [];
    if (!groups.length) {
        return null;
    }

    const definition = buildAnalysisChartDefinitions(1)[0] || {
        title: "Top themes",
        caption: "Distribution of responses across the top themes.",
        kind: "group",
    };
    const dimensions = resolveAnalysisExportDimensions({
        definition,
        fallbackWidth: 1200,
        fallbackHeight: Math.max(1170, groups.length * 78 + 230),
    });
    const plotSurface = document.createElement("div");
    plotSurface.style.position = "fixed";
    plotSurface.style.left = "-10000px";
    plotSurface.style.top = "0";
    plotSurface.style.pointerEvents = "none";
    plotSurface.style.width = `${dimensions.width}px`;
    plotSurface.style.height = `${dimensions.height}px`;
    document.body.appendChild(plotSurface);

    try {
        await plotly.newPlot(
            plotSurface,
            buildGeneratedGroupBarData(groups),
            buildGeneratedGroupBarLayout(groups, dimensions),
            {
                displaylogo: false,
                responsive: false,
                staticPlot: true,
            },
        );
        return {
            title: definition.title || "Top themes",
            caption: definition.caption || "Distribution of responses across the top themes.",
            image_data_url: await captureAnalysisChartImage(plotly, plotSurface, {
                width: dimensions.width,
                height: dimensions.height,
                definition,
            }),
        };
    } catch (error) {
        console.warn("[Verbatim App] Failed to generate the export bar chart; the report will skip that chart.", error);
        return null;
    } finally {
        if (typeof plotly.purge === "function") {
            plotly.purge(plotSurface);
        }
        plotSurface.remove();
    }
}


function buildGeneratedGroupBarData(groups) {
    return [
        {
            type: "bar",
            orientation: "h",
            y: groups.map((group) => group.label || "Unlabelled theme"),
            x: groups.map((group) => Number(group.count || 0)),
            text: groups.map((group) => String(Number(group.count || 0))),
            textposition: "outside",
            cliponaxis: false,
            marker: {
                color: groups.map((group) => group.is_noise ? "#9aa4b2" : "#2477F8"),
                line: {
                    color: groups.map((group) => group.is_noise ? "#818b98" : "#1b5dcc"),
                    width: 1,
                },
            },
            hovertemplate: [
                "<b>%{y}</b>",
                "Responses: %{x}",
                "<extra></extra>",
            ].join("<br>"),
        },
    ];
}


function buildGeneratedGroupBarLayout(groups, { width, height }) {
    const maxCount = Math.max(...groups.map((group) => Number(group.count || 0)), 1);
    return {
        width,
        height,
        autosize: false,
        margin: {
            t: 30,
            r: 110,
            b: 86,
            l: 360,
        },
        paper_bgcolor: "rgba(0, 0, 0, 0)",
        plot_bgcolor: "#ffffff",
        font: {
            family: "\"Segoe UI\", Aptos, sans-serif",
            color: "#172033",
            size: 12,
        },
        uniformtext: {
            minsize: 13,
            mode: "show",
        },
        bargap: 0.28,
        xaxis: {
            title: {
                text: "Responses",
            },
            gridcolor: "rgba(89, 104, 128, 0.12)",
            zeroline: false,
            range: [0, Math.ceil(maxCount * 1.1)],
            fixedrange: true,
        },
        yaxis: {
            automargin: true,
            autorange: "reversed",
            tickangle: 0,
            tickfont: {
                size: 14,
            },
            fixedrange: true,
        },
    };
}
