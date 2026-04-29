class IngestionError(Exception):
    """Base error for ingestion and transformation failures."""


class UnsupportedFileTypeError(IngestionError):
    """Raised when the uploaded file is not a CSV."""


class CsvDecodeError(IngestionError):
    """Raised when the uploaded CSV bytes cannot be decoded."""


class ManifestBuildError(IngestionError):
    """Raised when the architect cannot build a valid manifest."""


class RowLimitExceededError(IngestionError):
    """Raised when the transformed dataframe breaches the safety limit."""


class TopicAnalysisError(Exception):
    """Base error for topic-modeling analysis failures."""


class TopicAnalysisDependencyError(TopicAnalysisError):
    """Raised when an optional analysis dependency is unavailable."""


class TopicAnalysisRateLimitError(TopicAnalysisDependencyError):
    """Raised when a provider rate limit can be retried by the caller."""

    def __init__(self, message: str, *, error_code: str, retry_after_seconds: int) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.retry_after_seconds = retry_after_seconds


class TopicAnalysisInputError(TopicAnalysisError):
    """Raised when an analysis request cannot be satisfied with the selected data."""
