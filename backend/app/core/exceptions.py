"""
Base exception classes for the platform.

Each domain defines its own exceptions inheriting from these bases.
API layer maps these to HTTP responses.
"""


class PlatformError(Exception):
    """Base for all platform errors."""
    status_code: int = 500
    error_code: str = "internal_error"

    def __init__(self, message: str, detail: str | None = None) -> None:
        self.message = message
        self.detail = detail
        super().__init__(message)


class NotFoundError(PlatformError):
    status_code = 404
    error_code = "not_found"


class ForbiddenError(PlatformError):
    status_code = 403
    error_code = "forbidden"


class UnauthorizedError(PlatformError):
    status_code = 401
    error_code = "unauthorized"


class ValidationError(PlatformError):
    status_code = 422
    error_code = "validation_error"


class ConflictError(PlatformError):
    status_code = 409
    error_code = "conflict"


class PolicyViolationError(PlatformError):
    """Raised when content violates safety/policy rules."""
    status_code = 422
    error_code = "policy_violation"


class ConnectorError(PlatformError):
    """Raised when a source connector fails to fetch content."""
    status_code = 502
    error_code = "connector_error"


class IngestionError(PlatformError):
    """Raised when content ingestion fails."""
    status_code = 500
    error_code = "ingestion_error"
