"""Customer-scoped recipe similarity search and idempotent persistence."""

import asyncpg
from uuid import UUID

from app.db import to_vector_literal
from app.errors import NotFoundError, map_database_error
from app.schemas import (
    DuplicateCheckResult,
    RecipeDuplicateInput,
    RecipeMatch,
    RecipeSaveInput,
    RecipeSaveResult,
)

CUSTOMER_EXISTS_SQL = "SELECT EXISTS(SELECT 1 FROM customers WHERE id = $1)"
SIMILAR_RECIPES_SQL = """
    SELECT recipe_name, day_number, 1 - (embedding <=> $2::vector) AS similarity
    FROM recipe_history
    WHERE customer_id = $1 AND embedding IS NOT NULL
    ORDER BY embedding <=> $2::vector
    LIMIT $3
"""
SAVE_RECIPE_SQL = """
    INSERT INTO recipe_history
        (customer_id, recipe_name, day_number, ingredients, instructions, calories, embedding)
    VALUES ($1, $2, $3, $4, $5, $6, $7::vector)
    ON CONFLICT (customer_id, day_number) DO UPDATE SET
        recipe_name = EXCLUDED.recipe_name,
        ingredients = EXCLUDED.ingredients,
        instructions = EXCLUDED.instructions,
        calories = EXCLUDED.calories,
        embedding = EXCLUDED.embedding,
        generated_at = CURRENT_TIMESTAMP
    RETURNING id
"""


async def find_similar_recipes(
    pool: asyncpg.Pool,
    request: RecipeDuplicateInput,
) -> DuplicateCheckResult:
    """Search only the requested customer's recipe history."""
    vector = to_vector_literal(request.embedding)
    try:
        customer_exists = await pool.fetchval(CUSTOMER_EXISTS_SQL, request.customer_id)
        if not customer_exists:
            raise NotFoundError("Customer not found")
        rows = await pool.fetch(
            SIMILAR_RECIPES_SQL,
            request.customer_id,
            vector,
            request.limit,
        )
    except asyncpg.PostgresError as error:
        mapped_error = map_database_error(error)
        if mapped_error is not None:
            raise mapped_error from error
        raise
    matches = [RecipeMatch.model_validate(dict(row)) for row in rows]
    return DuplicateCheckResult(
        is_duplicate=any(item.similarity >= request.threshold for item in matches),
        matches=matches,
    )


async def insert_recipe(
    pool: asyncpg.Pool,
    request: RecipeSaveInput,
) -> RecipeSaveResult:
    """Insert or replace a customer's recipe for the requested day."""
    try:
        recipe_id = await pool.fetchval(
            SAVE_RECIPE_SQL,
            request.customer_id,
            request.recipe_name,
            request.day_number,
            request.ingredients,
            request.instructions,
            request.calories,
            to_vector_literal(request.embedding),
        )
    except asyncpg.PostgresError as error:
        mapped_error = map_database_error(error)
        if mapped_error is not None:
            raise mapped_error from error
        raise
    return RecipeSaveResult(id=UUID(str(recipe_id)))
