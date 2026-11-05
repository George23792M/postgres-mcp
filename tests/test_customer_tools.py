"""Customer profile repository behavior using a deterministic database fake."""

from uuid import UUID

import asyncpg
import pytest
from pydantic import ValidationError

from app.errors import ConflictError, DatabaseUnavailableError, NotFoundError
from app.repositories.customer_repository import (
    CUSTOMER_PROFILE_SQL,
    fetch_customer_profile,
)
from app.schemas import CustomerProfileInput


class FakeCustomerPool:
    """Record customer queries and return prearranged database rows."""

    def __init__(self, rows, error=None):
        """Store the rows or exception returned by the fake pool."""
        self.rows = rows
        self.error = error
        self.calls = []

    async def fetch(self, query, *args):
        """Record a parameterized query and return the configured rows."""
        self.calls.append((query, args))
        if self.error is not None:
            raise self.error
        return self.rows


def customer_row(customer_id, preference_id, profile_name, nut_free, gluten_free):
    """Build a database-shaped row with synthetic customer and preference data."""
    return {
        "id": customer_id,
        "first_name": "Taylor",
        "middle_name": None,
        "last_name": "Example",
        "preferred_name": "Tay",
        "email": "taylor@example.invalid",
        "is_active": True,
        "preference_id": preference_id,
        "profile_name": profile_name,
        "days": 7,
        "max_calories": 500,
        "nut_free": nut_free,
        "gluten_free": gluten_free,
        "dairy_free": False,
        "soy_free": False,
    }


@pytest.mark.asyncio
async def test_profile_returns_identity_and_derived_active_constraints(customer_id):
    """The profile combines active preference rows into sorted restriction labels."""
    rows = [
        customer_row(customer_id, UUID(int=1), "Default", True, False),
        customer_row(customer_id, UUID(int=2), "Gluten free", False, True),
    ]
    pool = FakeCustomerPool(rows)

    profile = await fetch_customer_profile(pool, customer_id)

    assert profile.id == customer_id
    assert profile.email == "taylor@example.invalid"
    assert [item.profile_name for item in profile.dietary_preferences] == [
        "Default",
        "Gluten free",
    ]
    assert profile.constraints == ["gluten-free", "nut-free"]
    assert pool.calls == [(CUSTOMER_PROFILE_SQL, (customer_id,))]
    assert "p.is_active IS TRUE" in CUSTOMER_PROFILE_SQL
    assert "c.is_active IS TRUE" in CUSTOMER_PROFILE_SQL


@pytest.mark.asyncio
async def test_profile_without_preferences_returns_empty_constraints(customer_id):
    """A customer with no active preference rows still receives a profile."""
    pool = FakeCustomerPool([customer_row(customer_id, None, None, False, False)])

    profile = await fetch_customer_profile(pool, customer_id)

    assert profile.dietary_preferences == []
    assert profile.constraints == []


@pytest.mark.asyncio
async def test_profile_not_found_for_unknown_or_inactive_customer(customer_id):
    """An empty active-customer query raises a safe not-found error."""
    pool = FakeCustomerPool([])

    with pytest.raises(NotFoundError, match="Customer not found or inactive"):
        await fetch_customer_profile(pool, customer_id)
    assert pool.calls[0][1] == (customer_id,)


def test_profile_input_rejects_sql_injection_instead_of_accepting_text():
    """Customer IDs are UUIDs, so SQL fragments are not accepted as identifiers."""
    with pytest.raises(ValidationError):
        CustomerProfileInput(customer_id="'; DROP TABLE customers; --")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("database_error", "expected_code"),
    [
        (asyncpg.ForeignKeyViolationError("SENSITIVE constraint and SQL"), "not_found"),
        (asyncpg.UniqueViolationError("SENSITIVE constraint and SQL"), "conflict"),
        (asyncpg.ConnectionFailureError("SENSITIVE connection detail"), "database_unavailable"),
    ],
)
async def test_profile_maps_known_database_failures_without_detail_leaks(
    customer_id, database_error, expected_code
):
    """Recognized customer-query errors become safe structured failures with causes."""
    pool = FakeCustomerPool([], error=database_error)

    with pytest.raises((NotFoundError, ConflictError, DatabaseUnavailableError)) as error:
        await fetch_customer_profile(pool, customer_id)

    assert error.value.code == expected_code
    assert error.value.__cause__ is database_error
    assert "SENSITIVE" not in error.value.safe_message
    assert "SENSITIVE" not in error.value.hint
    assert pool.calls == [(CUSTOMER_PROFILE_SQL, (customer_id,))]


@pytest.mark.asyncio
async def test_profile_propagates_unknown_sqlstate_unchanged(customer_id, unknown_database_error):
    """An unrecognized SQLSTATE remains the original exception at the customer boundary."""
    pool = FakeCustomerPool([], error=unknown_database_error)

    with pytest.raises(type(unknown_database_error)) as error:
        await fetch_customer_profile(pool, customer_id)

    assert error.value is unknown_database_error
    assert "synthetic sensitive database diagnostic" in str(error.value)
