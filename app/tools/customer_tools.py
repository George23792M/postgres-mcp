"""MCP customer profile lookup tool."""

from uuid import UUID

from app.db import get_pool
from app.repositories.customer_repository import fetch_customer_profile
from app.schemas import CustomerProfile, CustomerProfileInput


async def get_customer_profile(customer_id: UUID) -> CustomerProfile:
    """Return an active customer profile and active dietary preferences."""
    request = CustomerProfileInput(customer_id=customer_id)
    return await fetch_customer_profile(get_pool(), request.customer_id)
