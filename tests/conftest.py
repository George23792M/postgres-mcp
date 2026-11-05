"""Shared deterministic fixtures for Postgres MCP unit tests."""

import sys
from pathlib import Path
from uuid import UUID

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
    )


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
