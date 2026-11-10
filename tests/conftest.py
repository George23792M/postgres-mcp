"""Shared deterministic fixtures for Postgres MCP unit tests."""

import sys
from pathlib import Path
from uuid import UUID

import asyncpg
import pytest

# The source tree is not installed as a package; make the repository importable
# when pytest is launched through its Windows console-script entry point.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings


@pytest.fixture
def test_settings() -> Settings:
    """Provide explicit synthetic settings without loading environment files."""
    return Settings(
        _env_file=None,
        db_user="unit-test-user",
        db_password="synthetic-unit-test-password",
        db_host="127.0.0.1",
        db_port=5432,
        db_name="postgres_mcp_unit_test",
        mcp_auth_token="synthetic-token-for-unit-tests-only-0001",
        retry_max_attempts=3,
        retry_initial_wait_seconds=0.5,
        retry_max_wait_seconds=10.0,
        retry_multiplier=2.0,
    )


@pytest.fixture(autouse=True)
def initialize_retry_config(test_settings):
    """Initialize retry configuration before each test using test settings."""
    from app.retry import RetryConfig, set_retry_config
    retry_config = RetryConfig.from_settings(test_settings)
    set_retry_config(retry_config)


@pytest.fixture
def customer_id() -> UUID:
    """Return a stable synthetic customer identifier."""
    return UUID("00000000-0000-0000-0000-000000000101")


@pytest.fixture
def workflow_id() -> UUID:
    """Return a stable synthetic workflow identifier."""
    return UUID("00000000-0000-0000-0000-000000000202")


@pytest.fixture
def embedding() -> list[float]:
    """Return a finite, correctly dimensioned synthetic vector."""
    return [0.0] * 1536


class SyntheticPostgresError(asyncpg.PostgresError):
    """Provide an unknown SQLSTATE for repository propagation tests."""

    def __init__(self, sqlstate="99999", message="synthetic sensitive database diagnostic"):
        """Initialize an asyncpg-shaped exception without a database connection."""
        super().__init__(message)
        self._test_sqlstate = sqlstate

    @property
    def sqlstate(self):
        """Return the configured synthetic SQLSTATE."""
        return self._test_sqlstate


@pytest.fixture
def unknown_database_error():
    """Return a fresh unrecognized asyncpg error for propagation checks."""
    return SyntheticPostgresError()
