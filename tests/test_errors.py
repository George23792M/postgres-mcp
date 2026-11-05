"""Structured service error metadata and strict SQLSTATE mapping tests."""

import asyncpg
import pytest

from app.errors import (
    ConflictError,
    DatabaseUnavailableError,
    InvalidInputError,
    NotFoundError,
    ToolServiceError,
    map_database_error,
)


class SyntheticPostgresError(asyncpg.PostgresError):
    """Provide arbitrary synthetic SQLSTATEs without a live database."""

    def __init__(self, sqlstate, message="synthetic database diagnostic"):
        """Store the test SQLSTATE and diagnostic text."""
        super().__init__(message)
        self._test_sqlstate = sqlstate

    @property
    def sqlstate(self):
        """Return the SQLSTATE selected by the test."""
        return self._test_sqlstate


@pytest.mark.parametrize(
    ("error_type", "code", "retryable"),
    [
        (NotFoundError, "not_found", False),
        (ConflictError, "conflict", False),
        (DatabaseUnavailableError, "database_unavailable", True),
        (InvalidInputError, "invalid_input", False),
    ],
)
def test_service_errors_expose_stable_safe_metadata(error_type, code, retryable):
    """Each public service category has a stable and safe metadata contract."""
    error = error_type("SENSITIVE submitted value or database detail")

    assert isinstance(error, ToolServiceError)
    assert error.code == code
    assert error.safe_message
    assert error.hint
    assert error.retryable is retryable
    assert "SENSITIVE" not in error.safe_message
    assert "SENSITIVE" not in error.hint


def test_not_found_metadata_is_uniform_for_absent_and_inaccessible_resources():
    """Not-found metadata never signals whether an identifier exists or is owned."""
    missing = NotFoundError("Customer absent")
    inaccessible = NotFoundError("Workflow exists but is owned by someone else")

    assert (missing.code, missing.safe_message, missing.hint, missing.retryable) == (
        inaccessible.code,
        inaccessible.safe_message,
        inaccessible.hint,
        inaccessible.retryable,
    )


@pytest.mark.parametrize(
    ("sqlstate", "error_type", "code", "retryable"),
    [
        ("23503", asyncpg.ForeignKeyViolationError, "not_found", False),
        ("23505", asyncpg.UniqueViolationError, "conflict", False),
        ("08000", SyntheticPostgresError, "database_unavailable", True),
        ("08003", asyncpg.ConnectionDoesNotExistError, "database_unavailable", True),
        ("08006", asyncpg.ConnectionFailureError, "database_unavailable", True),
        ("57P01", asyncpg.AdminShutdownError, "database_unavailable", True),
        ("57P02", asyncpg.CrashShutdownError, "database_unavailable", True),
        ("57P03", asyncpg.CannotConnectNowError, "database_unavailable", True),
        ("53300", asyncpg.TooManyConnectionsError, "database_unavailable", True),
    ],
)
def test_database_mapper_translates_only_the_documented_sqlstates(
    sqlstate, error_type, code, retryable
):
    """The mapper implements each exact supported category with safe metadata."""
    error = (
        error_type(sqlstate, "SENSITIVE SQL SELECT credential")
        if error_type is SyntheticPostgresError
        else error_type("SENSITIVE SQL SELECT credential")
    )

    mapped = map_database_error(error)

    assert mapped is not None
    assert mapped.code == code
    assert mapped.retryable is retryable
    assert "SENSITIVE" not in mapped.safe_message
    assert "SENSITIVE" not in mapped.hint


@pytest.mark.parametrize("sqlstate", ["99999", "235030", "080000", "57P04", "533000"])
def test_database_mapper_does_not_translate_unlisted_sqlstates(sqlstate):
    """Unknown and prefix-like SQLSTATEs are returned unchanged by the mapper."""
    error = SyntheticPostgresError(sqlstate)

    assert map_database_error(error) is None


def test_database_mapper_ignores_non_asyncpg_errors():
    """An unrelated exception is never mislabeled as a database service error."""
    error = RuntimeError("synthetic failure")

    assert map_database_error(error) is None
