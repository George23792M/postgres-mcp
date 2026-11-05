"""Recipe search and save repository behavior at the database boundary."""

from uuid import UUID

import asyncpg
import pytest

from app.errors import ConflictError, DatabaseUnavailableError, NotFoundError
from app.repositories.recipe_repository import (
    CUSTOMER_EXISTS_SQL,
    SAVE_RECIPE_SQL,
    SIMILAR_RECIPES_SQL,
    find_similar_recipes,
    insert_recipe,
)
from app.schemas import RecipeDuplicateInput, RecipeSaveInput


class FakeRecipePool:
    """Record recipe SQL calls and return predetermined database values."""

    def __init__(
        self, *, exists=True, matches=None, saved_id=None, database_errors=None
    ):
        """Configure fake results and optional errors keyed by query operation."""
        database_errors = database_errors or {}
        self.exists = exists
        self.matches = matches or []
        self.saved_id = saved_id
        self.save_error = database_errors.get("save")
        self.exists_error = database_errors.get("exists")
        self.search_error = database_errors.get("search")
        self.calls = []
        self.fetchval_calls = 0

    async def fetchval(self, query, *args):
        """Record a scalar query and return the configured result."""
        self.calls.append((query, args))
        self.fetchval_calls += 1
        if query == CUSTOMER_EXISTS_SQL:
            if self.exists_error is not None:
                raise self.exists_error
            return self.exists
        if self.save_error is not None:
            raise self.save_error
        return self.saved_id

    async def fetch(self, query, *args):
        """Record a query and return the configured recipe matches."""
        self.calls.append((query, args))
        if self.search_error is not None:
            raise self.search_error
        return self.matches


def make_recipe_input(customer_id, embedding, **overrides):
    """Return a valid synthetic recipe input with optional field replacements."""
    values = {
        "customer_id": customer_id,
        "recipe_name": "Berry blend",
        "day_number": 1,
        "ingredients": "berries",
        "instructions": "Blend.",
        "embedding": embedding,
        "calories": 250,
    }
    return RecipeSaveInput(**(values | overrides))


@pytest.mark.asyncio
async def test_duplicate_search_is_customer_scoped_and_uses_threshold(customer_id, embedding):
    """A high-scoring match is flagged and the validated vector is a bound argument."""
    pool = FakeRecipePool(
        matches=[
            {"recipe_name": "Prior blend", "day_number": 2, "similarity": 0.95},
            {"recipe_name": "Other blend", "day_number": 3, "similarity": 0.60},
        ]
    )
    request = RecipeDuplicateInput(
        customer_id=customer_id,
        embedding=embedding,
        threshold=0.90,
        limit=2,
    )

    result = await find_similar_recipes(pool, request)

    assert result.is_duplicate is True
    assert [match.recipe_name for match in result.matches] == ["Prior blend", "Other blend"]
    assert pool.calls[0] == (CUSTOMER_EXISTS_SQL, (customer_id,))
    query, args = pool.calls[1]
    assert query == SIMILAR_RECIPES_SQL
    assert args == (customer_id, "[0.0," + ",".join(["0.0"] * 1535) + "]", 2)
    assert "WHERE customer_id = $1" in query


@pytest.mark.asyncio
async def test_duplicate_search_returns_false_for_no_match(customer_id, embedding):
    """A customer's history below the configured similarity threshold is not duplicate."""
    pool = FakeRecipePool(
        matches=[{"recipe_name": "Distant blend", "day_number": 1, "similarity": 0.89}]
    )

    result = await find_similar_recipes(
        pool,
        RecipeDuplicateInput(customer_id=customer_id, embedding=embedding, threshold=0.90),
    )

    assert result.is_duplicate is False
    assert len(result.matches) == 1


@pytest.mark.asyncio
async def test_duplicate_search_rejects_unknown_customer_without_search(customer_id, embedding):
    """An unknown customer fails before recipe similarity SQL is executed."""
    pool = FakeRecipePool(exists=False)

    with pytest.raises(NotFoundError, match="Customer not found"):
        await find_similar_recipes(
            pool,
            RecipeDuplicateInput(customer_id=customer_id, embedding=embedding),
        )

    assert pool.calls == [(CUSTOMER_EXISTS_SQL, (customer_id,))]


@pytest.mark.asyncio
async def test_recipe_save_binds_text_and_returns_upsert_identifier(customer_id, embedding):
    """Recipe content is parameterized and the id from the idempotent upsert is returned."""
    recipe_id = UUID("00000000-0000-0000-0000-000000000303")
    hostile_text = "name'); DROP TABLE recipe_history; --"
    pool = FakeRecipePool(saved_id=recipe_id)
    request = make_recipe_input(customer_id, embedding, recipe_name=hostile_text)

    result = await insert_recipe(pool, request)

    assert result.id == recipe_id
    query, args = pool.calls[0]
    assert query == SAVE_RECIPE_SQL
    assert args[1] == hostile_text
    assert hostile_text not in query
    assert "ON CONFLICT (customer_id, day_number) DO UPDATE" in query
    assert args[0] == customer_id


@pytest.mark.asyncio
async def test_recipe_save_maps_foreign_key_failure_to_not_found(customer_id, embedding):
    """A missing customer reported by the foreign key is returned as not found."""
    pool = FakeRecipePool(
        database_errors={"save": asyncpg.ForeignKeyViolationError("synthetic constraint")}
    )

    with pytest.raises(NotFoundError, match="Customer not found"):
        await insert_recipe(pool, make_recipe_input(customer_id, embedding))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "database_error", "expected_code"),
    [
        ("exists", asyncpg.ForeignKeyViolationError("SENSITIVE SQL detail"), "not_found"),
        ("search", asyncpg.ConnectionFailureError("SENSITIVE connection detail"), "database_unavailable"),
        ("save", asyncpg.UniqueViolationError("SENSITIVE constraint detail"), "conflict"),
    ],
)
async def test_recipe_database_failures_map_to_safe_categories(
    customer_id, embedding, operation, database_error, expected_code
):
    """Recipe reads and writes map known SQLSTATEs and preserve safe metadata."""
    from app.errors import ToolServiceError

    pool = FakeRecipePool(database_errors={operation: database_error})

    with pytest.raises(ToolServiceError) as error:
        if operation in ("exists", "search"):
            await find_similar_recipes(
                pool, RecipeDuplicateInput(customer_id=customer_id, embedding=embedding)
            )
        else:
            await insert_recipe(pool, make_recipe_input(customer_id, embedding))

    assert error.value.code == expected_code
    assert error.value.__cause__ is database_error
    assert "SENSITIVE" not in error.value.safe_message
    assert "SENSITIVE" not in error.value.hint


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["exists", "search", "save"])
async def test_recipe_repository_propagates_unknown_sqlstate(
    customer_id, embedding, operation, unknown_database_error
):
    """Every recipe query boundary propagates unknown asyncpg SQLSTATEs unchanged."""
    pool = FakeRecipePool(database_errors={operation: unknown_database_error})

    with pytest.raises(type(unknown_database_error)) as error:
        if operation in ("exists", "search"):
            await find_similar_recipes(
                pool, RecipeDuplicateInput(customer_id=customer_id, embedding=embedding)
            )
        else:
            await insert_recipe(pool, make_recipe_input(customer_id, embedding))

    assert error.value is unknown_database_error
