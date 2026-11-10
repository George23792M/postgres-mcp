"""Parameterized persistence operations for email templates."""

import asyncpg


async def active_email_template(pool: asyncpg.Pool, template_name: str) -> dict | None:
    """Return the active email template for a given name."""
    row = await pool.fetchrow(
        """SELECT id, template_name, subject, body_html FROM email_templates
           WHERE template_name = $1 AND status = 'ACTIVE' LIMIT 1""",
        template_name,
    )
    if row is None:
        return None
    return {
        "active": True,
        "subject": row["subject"],
        "html_body": row["body_html"],
    }
