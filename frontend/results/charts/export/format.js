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
