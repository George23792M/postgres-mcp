"""Parameterized customer profile queries."""

from uuid import UUID

import asyncpg

from app.errors import NotFoundError, map_database_error
from app.schemas import CustomerProfile, DietaryConstraints

CUSTOMER_PROFILE_SQL = """
    SELECT c.id, c.first_name, c.middle_name, c.last_name,
           c.preferred_name, c.email, c.is_active,
           p.id AS preference_id, p.profile_name, p.days, p.max_calories,
           p.nut_free, p.gluten_free, p.dairy_free, p.soy_free
    FROM customers AS c
    LEFT JOIN customer_preferences AS p
      ON p.customer_id = c.id AND p.is_active IS TRUE
    WHERE c.id = $1 AND c.is_active IS TRUE
    ORDER BY p.profile_name
"""


async def fetch_customer_profile(
    pool: asyncpg.Pool,
    customer_id: UUID,
) -> CustomerProfile:
    """Fetch an active customer and only their active preferences."""
    try:
        rows = await pool.fetch(CUSTOMER_PROFILE_SQL, customer_id)
    except asyncpg.PostgresError as error:
        mapped_error = map_database_error(error)
        if mapped_error is not None:
            raise mapped_error from error
        raise
    if not rows:
        raise NotFoundError("Customer not found or inactive")
    preferences = [_build_preference(row) for row in rows if row["preference_id"]]
    identity_fields = (
        "id", "first_name", "middle_name", "last_name",
        "preferred_name", "email", "is_active",
    )
    return CustomerProfile(
        **{key: rows[0][key] for key in identity_fields},
        dietary_preferences=preferences,
        constraints=sorted(
            {item for preference in preferences for item in preference.constraints}
        ),
    )


def _build_preference(row: asyncpg.Record) -> DietaryConstraints:
    """Map one active database preference into its validated model."""
    labels = {
        "nut_free": "nut-free",
        "gluten_free": "gluten-free",
        "dairy_free": "dairy-free",
        "soy_free": "soy-free",
    }
    constraints = [label for field, label in labels.items() if row[field]]
    return DietaryConstraints(
        profile_name=row["profile_name"],
        days=row["days"],
        max_calories=row["max_calories"],
        nut_free=row["nut_free"],
        gluten_free=row["gluten_free"],
        dairy_free=row["dairy_free"],
        soy_free=row["soy_free"],
        constraints=constraints,
    )
