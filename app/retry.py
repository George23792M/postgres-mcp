"""Centralized retry mechanism for database operations using tenacity."""

from collections.abc import Callable
from typing import Any, TypeVar

from loguru import logger
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.errors import DatabaseUnavailableError, map_database_error

Result = TypeVar("Result")


class RetryExhaustedError(Exception):
    """Raised when a database operation fails after all retry attempts are exhausted."""

    def __init__(self, operation_name: str, max_attempts: int, last_error: Exception) -> None:
        """Initialize with operation context and the last error encountered."""
        self.operation_name = operation_name
        self.max_attempts = max_attempts
        self.last_error = last_error
        super().__init__(
            f"Operation '{operation_name}' failed after {max_attempts} attempts: {type(last_error).__name__}"
        )


class RetryConfig:
    """Encapsulates retry behavior for database operations."""

    def __init__(
        self,
        max_attempts: int = 3,
        initial_wait_seconds: float = 0.5,
        max_wait_seconds: float = 10.0,
        multiplier: float = 2.0,
    ) -> None:
        """Initialize retry configuration with validated values."""
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if initial_wait_seconds <= 0:
            raise ValueError("initial_wait_seconds must be positive")
        if max_wait_seconds < initial_wait_seconds:
            raise ValueError("max_wait_seconds must be >= initial_wait_seconds")
        if multiplier < 1:
            raise ValueError("multiplier must be >= 1")

        self.max_attempts = max_attempts
        self.initial_wait_seconds = initial_wait_seconds
        self.max_wait_seconds = max_wait_seconds
        self.multiplier = multiplier

    @classmethod
    def from_settings(cls, settings: Any) -> "RetryConfig":
        """Load retry configuration from application settings."""
        return cls(
            max_attempts=settings.retry_max_attempts,
            initial_wait_seconds=settings.retry_initial_wait_seconds,
            max_wait_seconds=settings.retry_max_wait_seconds,
            multiplier=settings.retry_multiplier,
        )


_GLOBAL_RETRY_CONFIG: RetryConfig | None = None


def set_retry_config(config: RetryConfig) -> None:
    """Set the global retry configuration (called at application startup)."""
    global _GLOBAL_RETRY_CONFIG
    _GLOBAL_RETRY_CONFIG = config
    logger.info(
        "Retry config initialized: max_attempts={} initial_wait={:.1f}s max_wait={:.1f}s multiplier={:.1f}",
        config.max_attempts,
        config.initial_wait_seconds,
        config.max_wait_seconds,
        config.multiplier,
    )


def get_retry_config() -> RetryConfig:
    """Get the global retry configuration (raises if not initialized)."""
    if _GLOBAL_RETRY_CONFIG is None:
        raise RuntimeError("Retry configuration not initialized; call set_retry_config() at startup")
    return _GLOBAL_RETRY_CONFIG


async def with_database_retry(
    operation: Callable[[], Any],
    operation_name: str = "database operation",
) -> Any:
    """Execute a database operation with error translation and retry.

    This is the main entry point for tools: translate asyncpg errors, then apply retry logic.
    Only DatabaseUnavailableError is retried; other errors fail immediately.
    """
    config = get_retry_config()
    attempt_count = 0

    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(config.max_attempts),
        wait=wait_exponential(
            multiplier=config.multiplier,
            min=config.initial_wait_seconds,
            max=config.max_wait_seconds,
        ),
        retry=retry_if_exception_type(DatabaseUnavailableError),
        reraise=True,
    ):
        with attempt:
            attempt_count += 1
            try:
                return await _translate_database_errors(operation)
            except DatabaseUnavailableError as error:
                if attempt_count < config.max_attempts:
                    logger.warning(
                        "Database unavailable (attempt {}/{}): {}",
                        attempt_count,
                        config.max_attempts,
                        operation_name,
                    )
                else:
                    logger.error(
                        "Database operation failed after {} attempts: {}",
                        config.max_attempts,
                        operation_name,
                    )
                raise


async def _translate_database_errors(operation: Callable[[], Any]) -> Any:
    """Translate asyncpg errors to the server's safe error contract."""
    import asyncpg

    try:
        return await operation()
    except (OSError, TimeoutError, asyncpg.InterfaceError) as error:
        raise DatabaseUnavailableError() from error
    except asyncpg.PostgresError as error:
        mapped = map_database_error(error)
        if mapped is not None:
            raise mapped from error
        raise
