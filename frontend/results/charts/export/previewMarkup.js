// Markup builders and escaping helpers for the in-browser report preview.
export function buildDocumentPreviewMarkup(model, { format }) {
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


export function buildSlidesPreviewMarkup(model) {
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


export function toSafeScriptString(value) {
    return JSON.stringify(String(value || "")).replace(/</g, "\\u003c");
}


export function escapePreviewHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}


export function escapePreviewAttribute(value) {
    return escapePreviewHtml(value);
}
