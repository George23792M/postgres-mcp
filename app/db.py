"""Database pool lifecycle and pgvector formatting helpers."""

import math
from collections.abc import Sequence

import asyncpg
from loguru import logger

from app.config import Settings, get_settings

_pool: asyncpg.Pool | None = None


async def create_pool(settings: Settings | None = None) -> asyncpg.Pool:
    """Create the shared asyncpg pool using validated settings."""
    global _pool
    if _pool is not None:
        return _pool
    config = settings or get_settings()
    _pool = await asyncpg.create_pool(
        user=config.db_user,
        password=config.db_password.get_secret_value(),
        host=config.db_host,
        port=config.db_port,
        database=config.db_name,
        min_size=config.db_pool_min_size,
        max_size=config.db_pool_max_size,
        command_timeout=config.db_command_timeout,
    )
    logger.info("Database pool connected to {} / {}", config.db_host, config.db_name)
    return _pool


async def close_pool() -> None:
    """Close the shared pool and clear its module-level reference."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    """Return the initialized pool or fail clearly before startup."""
    if _pool is None:
        raise RuntimeError("Database pool has not been initialized")
    return _pool


def to_vector_literal(values: Sequence[float]) -> str:
    """Format finite numeric values as a pgvector text literal."""
    if not values:
        raise ValueError("Vector cannot be empty")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
        raise ValueError("Vector values must be finite numbers")
    numbers = [float(value) for value in values]
    if not all(math.isfinite(value) for value in numbers):
        raise ValueError("Vector values must be finite numbers")
    return f"[{','.join(map(str, numbers))}]"
