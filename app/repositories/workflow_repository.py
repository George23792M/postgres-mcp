"""Atomic workflow claiming and ownership-checked updates."""

import asyncpg

from app.errors import NotFoundError, map_database_error
from app.schemas import (
    ClaimWorkflowInput,
    WorkflowClaim,
    WorkflowStatusUpdate,
    WorkflowUpdateResult,
)

CLAIM_PENDING_SQL = """
    SELECT id, customer_id, status, attempt_count, validation_errors,
           email_status, workflow_type, started_at
    FROM workflow_runs
    WHERE workflow_type = $1 AND status = 'PENDING'
    ORDER BY started_at ASC
    LIMIT 1
    FOR UPDATE SKIP LOCKED
"""
SET_WORKFLOW_RUNNING_SQL = """
    UPDATE workflow_runs
    SET status = 'RUNNING', claimed_by = $2, updt_ts = CURRENT_TIMESTAMP
    WHERE id = $1
    RETURNING id, customer_id, status, attempt_count, validation_errors,
              email_status, workflow_type, started_at, claimed_by
"""
UPDATE_WORKFLOW_SQL = """
    UPDATE workflow_runs
    SET status = $3,
        attempt_count = LEAST(attempt_count + CASE WHEN $4 THEN 1 ELSE 0 END, 3),
        validation_errors = COALESCE($5, validation_errors),
        email_status = COALESCE($6, email_status),
        completed_at = CASE WHEN $3 IN ('SUCCESS', 'FAILED')
                            THEN CURRENT_TIMESTAMP ELSE NULL END,
        updt_ts = CURRENT_TIMESTAMP
    WHERE id = $1 AND claimed_by = $2
    RETURNING id, status, attempt_count, email_status
"""


async def claim_pending_workflow(
    pool: asyncpg.Pool,
    request: ClaimWorkflowInput,
) -> WorkflowClaim | None:
    """Claim the oldest pending workflow without blocking other workers."""
    try:
        async with pool.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    CLAIM_PENDING_SQL,
                    request.workflow_type.value,
                )
                if row is None:
                    return None
                claimed = await connection.fetchrow(
                    SET_WORKFLOW_RUNNING_SQL,
                    row["id"],
                    request.worker_id,
                )
    except asyncpg.PostgresError as error:
        mapped_error = map_database_error(error)
        if mapped_error is not None:
            raise mapped_error from error
        raise
    return WorkflowClaim.model_validate(dict(claimed))


async def update_workflow_status(
    pool: asyncpg.Pool,
    request: WorkflowStatusUpdate,
) -> WorkflowUpdateResult:
    """Update a claimed row only when the worker still owns it."""
    try:
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                UPDATE_WORKFLOW_SQL,
                request.workflow_id,
                request.worker_id,
                request.status.value,
                request.increment_attempt,
                request.validation_errors,
                request.email_status.value if request.email_status else None,
            )
    except asyncpg.PostgresError as error:
        mapped_error = map_database_error(error)
        if mapped_error is not None:
            raise mapped_error from error
        raise
    if row is None:
        raise NotFoundError("Workflow not found or not owned by this worker")
    return WorkflowUpdateResult.model_validate(dict(row))
