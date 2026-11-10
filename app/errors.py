"""Structured, client-safe service errors and database error mapping."""

import asyncpg


class ToolServiceError(Exception):
    """Base class for expected tool failures with safe stable metadata."""

    code = "tool_error"
    safe_message = "The tool request could not be completed."
    hint = "Review the request and try again if appropriate."
    retryable = False

    def __init__(self, message: str | None = None) -> None:
        """Initialize an error, retaining optional legacy text for local callers."""
        super().__init__(message or self.safe_message)


class NotFoundError(ToolServiceError):
    """Represent absent or inaccessible resources without distinguishing them."""

    code = "not_found"
    safe_message = "The requested resource was not found."
    hint = "Verify the identifier and your access to the requested resource."


class ConflictError(ToolServiceError):
    """Represent a request that conflicts with persisted application state."""

    code = "conflict"
    safe_message = "The request conflicts with the current resource state."
    hint = "Refresh the resource state before submitting a different request."


class DatabaseUnavailableError(ToolServiceError):
    """Represent an allow-listed transient database availability failure."""

    code = "database_unavailable"
    safe_message = "The service is temporarily unable to access its database."
    hint = "Retry later with a bounded delay; do not retry indefinitely."
    retryable = True


class RetryExhaustedError(ToolServiceError):
    """Transient database error persisted after all retry attempts were exhausted."""

    code = "retry_exhausted"
    safe_message = "The database was unavailable; retries exhausted."
    hint = "The service is experiencing persistent connectivity issues. Retry after a longer delay or contact support if the problem persists."
    retryable = False

    def __init__(
        self,
        operation_name: str,
        max_attempts: int,
        last_error: Exception | None = None,
    ) -> None:
        """Initialize with retry exhaustion context."""
        self.operation_name = operation_name
        self.max_attempts = max_attempts
        self.last_error = last_error
        details = f"Operation: {operation_name}, Attempts: {max_attempts}"
        super().__init__(details)


class InvalidInputError(ToolServiceError):
    """Represent invalid tool input without exposing validation internals."""

    code = "invalid_input"
    safe_message = "The tool input is invalid."
    hint = "Check the documented fields and constraints, then correct the request."


_SQLSTATE_ERROR_TYPES: dict[str, type[ToolServiceError]] = {
    "23503": NotFoundError,
    "23505": ConflictError,
    **{
        sqlstate: DatabaseUnavailableError
        for sqlstate in (
            "08000", "08003", "08006", "57P01", "57P02", "57P03", "53300"
        )
    },
}


def map_database_error(error: Exception) -> ToolServiceError | None:
    """Map only explicitly supported asyncpg SQLSTATEs to safe service errors.

    Args:
        error: The original exception raised by an asyncpg operation.

    Returns:
        A structured error for a supported SQLSTATE, or None when unmapped.
    """
    if not isinstance(error, asyncpg.PostgresError):
        return None
    sqlstate = error.sqlstate or ""
    error_type = _SQLSTATE_ERROR_TYPES.get(sqlstate)
    if error_type is None:
        return None
    legacy_text = {
        "23503": "Customer not found",
        "23505": "Workflow status conflicts with an active run",
    }.get(sqlstate)
    return error_type(legacy_text)
