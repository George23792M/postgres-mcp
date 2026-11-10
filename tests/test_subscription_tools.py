"""Tests for subscription workflow contracts and database boundaries."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.errors import ConflictError, DatabaseUnavailableError, NotFoundError
from app.repositories.subscription_repository import (
    CUSTOMER_SQL,
    claim_reconciliation,
    complete_batch,
    customer_context,
    finish_registration,
)
from app.schemas_subscription import BatchCompletion, RegistrationCompletion
from app.tools.subscription_tools import _database_result


@pytest.mark.asyncio
async def test_claim_reconciliation_returns_state_without_customer_data():
    """Operators can locate uncertain work using only the claim request ID."""
    pool = AsyncMock()
    request_id, workflow_id = uuid4(), uuid4()
    pool.fetchrow.return_value = {
        "request_id": request_id, "worker_id": "worker", "completed": True,
        "workflow_id": workflow_id, "workflow_status": "RUNNING", "email_status": "PENDING",
    }
    result = await claim_reconciliation(pool, request_id)
    assert result.workflow_id == workflow_id
    assert result.workflow_status == "RUNNING"
    assert "customer_id" not in result.model_dump()


@pytest.mark.asyncio
async def test_claim_reconciliation_rejects_missing_request():
    """An absent request is distinct from a recorded empty claim."""
    pool = AsyncMock()
    pool.fetchrow.return_value = None
    with pytest.raises(NotFoundError):
        await claim_reconciliation(pool, uuid4())


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [TimeoutError(), OSError(),])
async def test_database_transport_failure_is_safe(error):
    """Database transport failures have a safe availability classification."""
    async def fail():
        """Raise the simulated database transport failure."""
        raise error

    with pytest.raises(DatabaseUnavailableError):
        await _database_result(fail())


def test_subscription_customer_query_selects_latest_active_plan():
    """The lookup must use a stable timestamp and ID tie breaker."""
    assert "status = 'ACTIVE'" in CUSTOMER_SQL
    assert "ORDER BY cre_ts DESC, id DESC" in CUSTOMER_SQL


@pytest.mark.asyncio
async def test_customer_context_missing_active_subscription_raises_not_found():
    """A missing active subscription never yields a fabricated plan."""
    pool = AsyncMock()
    pool.fetchrow.return_value = None

    with pytest.raises(NotFoundError):
        await customer_context(pool, uuid4())


@pytest.mark.parametrize(
    ("status", "email_status"),
    [("SUCCESS", "PENDING"), ("SUCCESS", "FAILED"), ("FAILED", "SENT")],
)
def test_registration_completion_rejects_unconfirmed_success(status, email_status):
    """The database must not record a workflow as sent without confirmation."""
    with pytest.raises(ValidationError):
        RegistrationCompletion(status=status, email_status=email_status)


def test_batch_completion_rejects_inconsistent_counts():
    """Batch totals must equal the sum of outcome counters."""
    with pytest.raises(ValidationError):
        BatchCompletion(
            status="SUCCESS", total_customers=2, successful_count=1,
            failed_count=0, skipped_count=0,
        )


@pytest.mark.asyncio
async def test_completion_replay_does_not_increment_attempt_count():
    """Replaying the same terminal update returns the existing result."""
    pool = AsyncMock()
    workflow_id = uuid4()
    customer_id = uuid4()
    now = datetime.now(timezone.utc)
    row = {
        "id": workflow_id, "customer_id": customer_id,
        "workflow_type": "NEW_REGISTRATION", "status": "SUCCESS",
        "email_status": "SENT", "attempt_count": 1, "started_at": now,
        "completed_at": now, "validation_errors": None,
    }
    pool.fetchrow.side_effect = [None, row]

    result = await finish_registration(
        pool, workflow_id, "worker", RegistrationCompletion(status="SUCCESS", email_status="SENT")
    )

    assert result.attempt_count == 1
    assert pool.fetchrow.await_count == 2


@pytest.mark.asyncio
async def test_completion_rejects_update_by_non_owner():
    """Absent and non-owned workflow rows have the same safe error."""
    pool = AsyncMock()
    pool.fetchrow.side_effect = [None, None]

    with pytest.raises(NotFoundError):
        await finish_registration(
            pool, uuid4(), "worker", RegistrationCompletion(status="FAILED", email_status="FAILED")
        )


@pytest.mark.asyncio
async def test_batch_completion_rejects_conflicting_replay():
    """A terminal batch cannot be overwritten with different counts."""
    pool = AsyncMock()
    now = datetime.now(timezone.utc)
    batch_id = uuid4()
    pool.fetchrow.side_effect = [
        None,
        {
            "id": batch_id, "batch_type": "NEW_REGISTRATION", "status": "SUCCESS",
            "total_customers": 1, "successful_count": 1, "failed_count": 0,
            "skipped_count": 0, "started_at": now, "completed_at": now,
            "error_message": None,
        },
    ]
    completion = BatchCompletion(
        status="SUCCESS", total_customers=0, successful_count=0,
        failed_count=0, skipped_count=0,
    )

    with pytest.raises(ConflictError):
        await complete_batch(pool, batch_id, completion)
