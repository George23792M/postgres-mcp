"""MCP tools for email template retrieval."""

from typing import Annotated, Any

from pydantic import Field

from app.db import get_pool
from app.repositories import email_repository as repository
from app.retry import with_database_retry


async def get_active_email_template(
    template_name: Annotated[str, Field(min_length=1, max_length=100)],
) -> dict[str, Any]:
    """Return the active email template for a given name or not-found marker."""
    template = await with_database_retry(
        lambda: repository.active_email_template(get_pool(), template_name),
        "get_active_email_template",
    )
    if template is None:
        return {"found": False}
    return {"found": True, "template": template}

