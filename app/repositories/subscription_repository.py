"""Parameterized persistence operations for subscription workflows."""

from uuid import UUID

import asyncpg

from app.errors import ConflictError, NotFoundError
from app.schemas_subscription import BatchCompletion, BatchRun, ClaimReconciliation, RegistrationCompletion, SubscriptionCustomer
from app.schemas_subscription import SubscriptionClaim, WorkflowHistoryEntry

CUSTOMER_SQL = """
    SELECT c.id AS customer_id, c.first_name, c.last_name, c.preferred_name,
           c.email, s.plan_name
    FROM customers c
    JOIN LATERAL (
        SELECT plan_name FROM subscriptions
        WHERE customer_id = c.id AND status = 'ACTIVE'
        ORDER BY cre_ts DESC, id DESC LIMIT 1
    ) s ON TRUE
    WHERE c.id = $1 AND c.is_active IS TRUE
"""

HISTORY_SQL = """
    SELECT id, customer_id, workflow_type, status, email_status, attempt_count,
           started_at, completed_at, validation_errors
    FROM workflow_runs
    WHERE customer_id = $1 AND ($2::text IS NULL OR workflow_type = $2)
    ORDER BY started_at DESC, id DESC LIMIT $3
"""

CLAIM_FIELDS = "id, customer_id, claimed_by, workflow_type, status, attempt_count"
CLAIM_SQL = f"""
    SELECT id FROM workflow_runs
    WHERE workflow_type = 'NEW_REGISTRATION' AND status = 'PENDING'
      AND ($1::uuid IS NULL OR customer_id = $1)
    ORDER BY started_at ASC, id ASC LIMIT 1 FOR UPDATE SKIP LOCKED
"""
START_SQL = f"""
    UPDATE workflow_runs SET status = 'RUNNING', claimed_by = $2,
        completed_at = NULL, updt_ts = CURRENT_TIMESTAMP
    WHERE id = $1 AND status = 'PENDING' RETURNING {CLAIM_FIELDS}
"""


async def customer_context(pool: asyncpg.Pool, customer_id: UUID) -> SubscriptionCustomer:
    """Return an active customer and the newest active subscription."""
    row = await pool.fetchrow(CUSTOMER_SQL, customer_id)
    if row is None:
        raise NotFoundError()
    return SubscriptionCustomer.model_validate(dict(row))


async def workflow_history(
    pool: asyncpg.Pool, customer_id: UUID, workflow_type: str | None, limit: int
) -> list[WorkflowHistoryEntry]:
    """List a customer's workflow history in reverse chronological order."""
    rows = await pool.fetch(HISTORY_SQL, customer_id, workflow_type, limit)
    return [WorkflowHistoryEntry.model_validate(dict(row)) for row in rows]


async def claim_reconciliation(pool: asyncpg.Pool, request_id: UUID) -> ClaimReconciliation:
    """Find a recorded claim and its current status without exposing customer data."""
    row = await pool.fetchrow(
        """SELECT r.request_id, r.worker_id, r.completed, r.workflow_id,
                  w.status AS workflow_status, w.email_status
           FROM subscription_claim_requests r
           LEFT JOIN workflow_runs w ON w.id = r.workflow_id
           WHERE r.request_id = $1""",
        request_id,
    )
    if row is None:
        raise NotFoundError()
    return ClaimReconciliation.model_validate(dict(row))


async def claim_registration(
    pool: asyncpg.Pool, request_id: UUID, worker_id: str, customer_id: UUID | None
) -> SubscriptionClaim | None:
    """Atomically claim a queued registration and replay identical requests."""
    async with pool.acquire() as connection:
        async with connection.transaction():
            return await _claim_transaction(connection, request_id, worker_id, customer_id)


async def _claim_transaction(
    connection: asyncpg.Connection, request_id: UUID, worker_id: str, customer_id: UUID | None
) -> SubscriptionClaim | None:
    """Serialize a claim request and store its result within one transaction."""
    await connection.execute(
        """INSERT INTO subscription_claim_requests
           (request_id, worker_id, workflow_type, customer_id)
           VALUES ($1, $2, 'NEW_REGISTRATION', $3) ON CONFLICT DO NOTHING""",
        request_id, worker_id, customer_id,
    )
    request = await connection.fetchrow(
        "SELECT * FROM subscription_claim_requests WHERE request_id = $1 FOR UPDATE",
        request_id,
    )
    if request["worker_id"] != worker_id or request["customer_id"] != customer_id:
        raise ConflictError()
    if request["completed"]:
        return await _replay_claim(connection, request["workflow_id"])
    claim = await _claim_next(connection, worker_id, customer_id)
    await connection.execute(
        "UPDATE subscription_claim_requests SET completed = TRUE, workflow_id = $2 WHERE request_id = $1",
        request_id, claim.id if claim else None,
    )
    return claim


async def _replay_claim(
    connection: asyncpg.Connection, workflow_id: UUID | None
) -> SubscriptionClaim | None:
    """Replay a previously completed claim without claiming another row."""
    if workflow_id is None:
        return None
    row = await connection.fetchrow(
        f"SELECT {CLAIM_FIELDS} FROM workflow_runs WHERE id = $1", workflow_id
    )
    if row is None or row["status"] != "RUNNING":
        raise ConflictError()
    return SubscriptionClaim.model_validate(dict(row))


async def _claim_next(
    connection: asyncpg.Connection, worker_id: str, customer_id: UUID | None
) -> SubscriptionClaim | None:
    """Claim one pending workflow, optionally creating a new targeted run."""
    if customer_id is not None:
        await _create_target_if_missing(connection, customer_id)
    row = await connection.fetchrow(CLAIM_SQL, customer_id)
    if row is None:
        return None
    claimed = await connection.fetchrow(START_SQL, row["id"], worker_id)
    return SubscriptionClaim.model_validate(dict(claimed))


async def _create_target_if_missing(connection: asyncpg.Connection, customer_id: UUID) -> None:
    """Create an on-demand registration only when no prior run exists."""
    customer = await connection.fetchrow(
        "SELECT id FROM customers WHERE id = $1 AND is_active IS TRUE FOR UPDATE", customer_id
    )
    if customer is None:
        raise NotFoundError()
    await connection.execute(
        """INSERT INTO workflow_runs (customer_id, workflow_type, status, email_status, attempt_count)
           SELECT $1, 'NEW_REGISTRATION', 'PENDING', 'PENDING', 0
           WHERE NOT EXISTS (
               SELECT 1 FROM workflow_runs
               WHERE customer_id = $1 AND workflow_type = 'NEW_REGISTRATION'
           ) ON CONFLICT DO NOTHING""",
        customer_id,
    )


async def finish_registration(
    pool: asyncpg.Pool, workflow_id: UUID, worker_id: str, result: RegistrationCompletion
) -> WorkflowHistoryEntry:
    """Complete an owned running workflow or replay its identical terminal update."""
    row = await pool.fetchrow(
        """UPDATE workflow_runs SET status = $3, email_status = $4,
           validation_errors = $5, attempt_count = LEAST(attempt_count + 1, 3),
           completed_at = CURRENT_TIMESTAMP, updt_ts = CURRENT_TIMESTAMP
           WHERE id = $1 AND claimed_by = $2 AND status = 'RUNNING'
           RETURNING id, customer_id, workflow_type, status, email_status, attempt_count,
                     started_at, completed_at, validation_errors""",
        workflow_id, worker_id, result.status, result.email_status, result.error_message,
    )
    if row is not None:
        return WorkflowHistoryEntry.model_validate(dict(row))
    return await _replay_completion(pool, workflow_id, worker_id, result)


async def _replay_completion(
    pool: asyncpg.Pool, workflow_id: UUID, worker_id: str, result: RegistrationCompletion
) -> WorkflowHistoryEntry:
    """Return a matching completion without updating attempts a second time."""
    row = await pool.fetchrow(
        """SELECT id, customer_id, workflow_type, status, email_status, attempt_count,
                  started_at, completed_at, validation_errors
           FROM workflow_runs WHERE id = $1 AND claimed_by = $2""",
        workflow_id, worker_id,
    )
    if row is None:
        raise NotFoundError()
    if (row["status"], row["email_status"], row["validation_errors"]) != (
        result.status, result.email_status, result.error_message
    ):
        raise ConflictError()
    return WorkflowHistoryEntry.model_validate(dict(row))


async def create_batch(pool: asyncpg.Pool, batch_id: UUID) -> BatchRun:
    """Create or safely replay a registration batch creation."""
    row = await pool.fetchrow(
        """INSERT INTO batch_runs (id, batch_type) VALUES ($1, 'NEW_REGISTRATION')
           ON CONFLICT (id) DO UPDATE SET id = EXCLUDED.id RETURNING *""",
        batch_id,
    )
    return BatchRun.model_validate(dict(row))


async def complete_batch(pool: asyncpg.Pool, batch_id: UUID, result: BatchCompletion) -> BatchRun:
    """Complete a running batch; replay the same terminal result safely."""
    row = await pool.fetchrow(
        """UPDATE batch_runs SET status = $2, total_customers = $3,
           successful_count = $4, failed_count = $5, skipped_count = $6,
           error_message = $7, completed_at = CURRENT_TIMESTAMP
           WHERE id = $1 AND status = 'RUNNING' RETURNING *""",
        batch_id, result.status, result.total_customers, result.successful_count,
        result.failed_count, result.skipped_count, result.error_message,
    )
    if row is not None:
        return BatchRun.model_validate(dict(row))
    existing = await pool.fetchrow("SELECT * FROM batch_runs WHERE id = $1", batch_id)
    if existing is None:
        raise NotFoundError()
    batch = BatchRun.model_validate(dict(existing))
    if any(getattr(batch, name) != value for name, value in result.model_dump().items()):
        raise ConflictError()
    return batch


async def batch_history(pool: asyncpg.Pool, limit: int) -> list[BatchRun]:
    """List recent batch summaries in reverse chronological order."""
    rows = await pool.fetch(
        "SELECT * FROM batch_runs ORDER BY started_at DESC, id DESC LIMIT $1", limit
    )
    return [BatchRun.model_validate(dict(row)) for row in rows]
