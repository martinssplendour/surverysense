from app.features.export.report_export_service.service import (
    AnalysisReportExportService,
    ExportedReportArtifact,
)

__all__ = [
    "AnalysisReportExportService",
    "DecodedChartImage",
    "ExportedReportArtifact",
]


def __getattr__(name: str):
    if name == "DecodedChartImage":
        from app.features.export.report_export_service.chart_image import DecodedChartImage

        return DecodedChartImage
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
