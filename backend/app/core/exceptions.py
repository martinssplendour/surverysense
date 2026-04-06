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
