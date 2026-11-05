"""Configuration validation and secret-redaction tests."""

import pytest
from pydantic import ValidationError

from app.config import Settings


def settings_values():
    """Return explicit synthetic non-secret settings for isolated validation."""
    return {
        "_env_file": None,
        "db_user": "unit-test-user",
        "db_password": "synthetic-password-for-tests",
        "db_host": "127.0.0.1",
        "db_port": 5432,
        "db_name": "postgres_mcp_unit_test",
    }


def test_settings_require_auth_token_without_loading_environment(monkeypatch):
    """A missing bearer token is a validation failure, independent of .env."""
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)

    with pytest.raises(ValidationError):
        Settings(**settings_values())


def test_settings_require_database_password_without_loading_environment(monkeypatch):
    """A missing database password is rejected without consulting local .env."""
    monkeypatch.delenv("DB_PASSWORD", raising=False)
    values = settings_values()
    values.pop("db_password")

    with pytest.raises(ValidationError):
        Settings(**values, mcp_auth_token="synthetic-token-for-unit-tests-only-0001")


def test_settings_repr_redacts_database_password_and_bearer_token():
    """SecretStr configuration fields never appear as plaintext in repr."""
    password = "synthetic-password-for-tests"
    token = "synthetic-token-for-unit-tests-only-0001"
    settings = Settings(
        **settings_values(),
        mcp_auth_token=token,
    )

    rendered = repr(settings)

    assert password not in rendered
    assert token not in rendered
    assert "**********" in rendered


def test_settings_reject_pool_minimum_above_maximum():
    """Pool sizing rejects a maximum smaller than the minimum."""
    with pytest.raises(ValidationError, match="DB_POOL_MAX_SIZE"):
        Settings(
            **settings_values(),
            mcp_auth_token="synthetic-token-for-unit-tests-only-0001",
            db_pool_min_size=5,
            db_pool_max_size=4,
        )
