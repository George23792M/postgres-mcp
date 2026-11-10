"""Tests for centralized retry mechanism."""

from unittest.mock import AsyncMock

import pytest

from app.errors import DatabaseUnavailableError, NotFoundError
from app.retry import (
    RetryConfig,
    RetryExhaustedError,
    get_retry_config,
    set_retry_config,
    with_database_retry,
)


def test_retry_config_initialization():
    """Test RetryConfig validates and stores configuration."""
    config = RetryConfig(
        max_attempts=5, initial_wait_seconds=1.0, max_wait_seconds=30.0, multiplier=3.0
    )
    assert config.max_attempts == 5
    assert config.initial_wait_seconds == 1.0
    assert config.max_wait_seconds == 30.0
    assert config.multiplier == 3.0


def test_retry_config_validation():
    """Test RetryConfig rejects invalid values."""
    with pytest.raises(ValueError, match="max_attempts must be at least 1"):
        RetryConfig(max_attempts=0)

    with pytest.raises(ValueError, match="initial_wait_seconds must be positive"):
        RetryConfig(initial_wait_seconds=-1)

    with pytest.raises(ValueError, match="max_wait_seconds must be >= initial_wait_seconds"):
        RetryConfig(initial_wait_seconds=10.0, max_wait_seconds=5.0)

    with pytest.raises(ValueError, match="multiplier must be >= 1"):
        RetryConfig(multiplier=0.5)


def test_retry_config_from_settings():
    """Test RetryConfig loads from settings object."""
    settings = AsyncMock()
    settings.retry_max_attempts = 4
    settings.retry_initial_wait_seconds = 0.25
    settings.retry_max_wait_seconds = 5.0
    settings.retry_multiplier = 1.5

    config = RetryConfig.from_settings(settings)
    assert config.max_attempts == 4
    assert config.initial_wait_seconds == 0.25
    assert config.max_wait_seconds == 5.0
    assert config.multiplier == 1.5


def test_global_retry_config():
    """Test global retry config can be set and retrieved."""
    config = RetryConfig(max_attempts=3)
    set_retry_config(config)
    retrieved = get_retry_config()
    assert retrieved.max_attempts == 3


def test_get_retry_config_before_init():
    """Test get_retry_config raises before initialization."""
    from app import retry as retry_module

    original_config = retry_module._GLOBAL_RETRY_CONFIG
    try:
        retry_module._GLOBAL_RETRY_CONFIG = None
        with pytest.raises(RuntimeError, match="not initialized"):
            get_retry_config()
    finally:
        retry_module._GLOBAL_RETRY_CONFIG = original_config


@pytest.mark.asyncio
async def test_with_database_retry_success():
    """Test successful operation without retry."""
    set_retry_config(RetryConfig(max_attempts=3))
    operation = AsyncMock(return_value="success")
    result = await with_database_retry(operation, "test_op")
    assert result == "success"
    operation.assert_called_once()


@pytest.mark.asyncio
async def test_with_database_retry_non_retryable_error():
    """Test non-retryable errors fail immediately."""
    set_retry_config(RetryConfig(max_attempts=3))
    operation = AsyncMock(side_effect=NotFoundError())

    with pytest.raises(NotFoundError):
        await with_database_retry(operation, "test_op")

    operation.assert_called_once()


@pytest.mark.asyncio
async def test_with_database_retry_retryable_then_success():
    """Test retryable error followed by success."""
    set_retry_config(RetryConfig(max_attempts=3, initial_wait_seconds=0.01))
    operation = AsyncMock(side_effect=[DatabaseUnavailableError(), "success"])

    result = await with_database_retry(operation, "test_op")
    assert result == "success"
    assert operation.call_count == 2


@pytest.mark.asyncio
async def test_with_database_retry_exhausts_attempts():
    """Test retry exhaustion raises the last error."""
    set_retry_config(RetryConfig(max_attempts=2, initial_wait_seconds=0.01))
    operation = AsyncMock(side_effect=DatabaseUnavailableError())

    with pytest.raises(DatabaseUnavailableError):
        await with_database_retry(operation, "test_op")

    assert operation.call_count == 2


def test_retry_exhausted_error():
    """Test RetryExhaustedError initialization and attributes."""
    last_error = DatabaseUnavailableError()
    exc = RetryExhaustedError("test_operation", 3, last_error)
    
    assert exc.operation_name == "test_operation"
    assert exc.max_attempts == 3
    assert exc.last_error is last_error
    assert "test_operation" in str(exc)
    assert "3" in str(exc)
