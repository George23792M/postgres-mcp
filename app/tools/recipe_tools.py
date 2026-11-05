"""MCP tools for customer-scoped duplicate checks and recipe saves."""

from typing import Annotated
from uuid import UUID

from app.db import get_pool
from pydantic import Field
from app.repositories.recipe_repository import find_similar_recipes, insert_recipe
from app.schemas import (
    DuplicateCheckResult,
    RecipeDuplicateInput,
    RecipeSaveInput,
    RecipeSaveResult,
)


async def check_duplicate_recipe(
    customer_id: UUID,
    embedding: Annotated[list[float], Field(min_length=1536, max_length=1536)],
    threshold: Annotated[float, Field(gt=0, le=1)] = 0.90,
    limit: Annotated[int, Field(ge=1, le=20)] = 5,
) -> DuplicateCheckResult:
    """Check a customer's history for recipes above the similarity threshold."""
    request = RecipeDuplicateInput(
        customer_id=customer_id,
        embedding=embedding,
        threshold=threshold,
        limit=limit,
    )
    result = await find_similar_recipes(get_pool(), request)
    return result


async def save_recipe(
    customer_id: UUID,
    recipe_name: Annotated[str, Field(min_length=1, max_length=255)],
    day_number: Annotated[int, Field(ge=1)],
    ingredients: Annotated[str, Field(min_length=1, max_length=12000)],
    instructions: Annotated[str, Field(min_length=1, max_length=20000)],
    embedding: Annotated[list[float], Field(min_length=1536, max_length=1536)],
    calories: Annotated[int | None, Field(ge=0, le=10000)] = None,
) -> RecipeSaveResult:
    """Save recipe content and caller-provided embedding idempotently."""
    request = RecipeSaveInput(
        customer_id=customer_id,
        recipe_name=recipe_name,
        day_number=day_number,
        ingredients=ingredients,
        instructions=instructions,
        embedding=embedding,
        calories=calories,
    )
    result = await insert_recipe(get_pool(), request)
    return result
