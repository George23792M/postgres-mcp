"""Tests for database helper behavior without connecting to PostgreSQL."""

import math

import pytest

from app import db
from app.db import to_vector_literal


def test_to_vector_literal_formats_finite_values():
    """Finite integer and floating-point values form a compact vector literal."""
    assert to_vector_literal([0.1, 2, -3.25]) == "[0.1,2.0,-3.25]"


@pytest.mark.parametrize(
    "values",
    [[], [math.nan], [math.inf], [-math.inf], [True], ["1.0"], [None]],
)
def test_to_vector_literal_rejects_empty_or_invalid_values(values):
    """Empty, non-numeric, and non-finite vectors are rejected."""
    with pytest.raises(ValueError):
        to_vector_literal(values)


@pytest.mark.asyncio
async def test_pool_is_reused_and_closed_with_configured_limits(monkeypatch, test_settings):
    """Pool creation passes validated bounds once and shutdown closes the pool."""
    class FakePool:
        """Track whether the test pool has been closed."""

        closed = False

        async def close(self):
            """Record that the fake pool was closed."""
            self.closed = True

    pool = FakePool()
    calls = []

    async def create_fake_pool(**kwargs):
        """Capture pool arguments and return the deterministic fake."""
        calls.append(kwargs)
        return pool

    monkeypatch.setattr(db, "_pool", None)
    monkeypatch.setattr(db.asyncpg, "create_pool", create_fake_pool)

    first = await db.create_pool(test_settings)
    second = await db.create_pool(test_settings)

    assert first is second is pool
    assert len(calls) == 1
    assert calls[0]["min_size"] == test_settings.db_pool_min_size
    assert calls[0]["max_size"] == test_settings.db_pool_max_size
    assert calls[0]["command_timeout"] == test_settings.db_command_timeout
    assert db.get_pool() is pool

    await db.close_pool()

    assert pool.closed is True
    with pytest.raises(RuntimeError, match="not been initialized"):
        db.get_pool()
