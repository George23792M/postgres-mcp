"""Safe service errors exposed to MCP clients."""


class ToolServiceError(Exception):
    """Base class for expected errors with client-safe messages."""


class NotFoundError(ToolServiceError):
    """Raised when a requested customer or workflow cannot be found."""


class ConflictError(ToolServiceError):
    """Raised when a requested change conflicts with persisted state."""
