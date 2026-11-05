"""Workflow claim and ownership behavior using a database boundary fake."""

from datetime import UTC, datetime
from uuid import UUID

import asyncpg
import pytest

from app.errors import ConflictError, DatabaseUnavailableError, NotFoundError, ToolServiceError
from app.repositories.workflow_repository import (
    CLAIM_PENDING_SQL,
    SET_WORKFLOW_RUNNING_SQL,
    UPDATE_WORKFLOW_SQL,
    claim_pending_workflow,
    update_workflow_status,
)
from app.schemas import (
    ClaimWorkflowInput,
    WorkflowStatus,
    WorkflowStatusUpdate,
    WorkflowType,
)


def workflow_row(workflow_id, customer_id, **overrides):
    """Build a valid synthetic workflow database result."""
    row = {
        "id": workflow_id,
        "customer_id": customer_id,
        "status": "RUNNING",
        "attempt_count": 1,
        "validation_errors": None,
        "email_status": "PENDING",
        "workflow_type": "NEW_REGISTRATION",
        "started_at": datetime(2026, 1, 1, tzinfo=UTC),
        "claimed_by": "worker-a",
    }
    return row | overrides


async def _run_workflow_operation(operation, connection, workflow_id):
    """Run the selected workflow repository operation against a fake connection."""
    pool = FakeWorkflowPool(connection)
    if operation.startswith("claim"):
        request = ClaimWorkflowInput(
            workflow_type=WorkflowType.NEW_REGISTRATION,
            worker_id="worker-a",
        )
        return await claim_pending_workflow(pool, request)
    request = WorkflowStatusUpdate(
        workflow_id=workflow_id,
        worker_id="worker-a",
        status=WorkflowStatus.PENDING,
    )
    return await update_workflow_status(pool, request)


class FakeTransaction:
    """Provide an async transaction context for repository tests."""

    async def __aenter__(self):
        """Return this transaction context."""
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        """Allow exceptions to propagate from the fake transaction."""
        return False


class FakeConnection:
    """Record SQL and return queued fetchrow results or errors."""

    def __init__(self, results):
        """Initialize queued results and an empty query log."""
        self.results = list(results)
        self.calls = []

    def transaction(self):
        """Return a fake async transaction context."""
        return FakeTransaction()

    async def fetchrow(self, query, *args):
        """Record the query and return or raise its next configured result."""
        self.calls.append((query, args))
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class FakeAcquire:
    """Return one deterministic fake connection from pool acquisition."""

    def __init__(self, connection):
        """Store the connection returned by this acquisition context."""
        self.connection = connection

    async def __aenter__(self):
        """Return the configured connection."""
        return self.connection

    async def __aexit__(self, exc_type, exc, traceback):
        """Allow exceptions to propagate from the fake acquisition."""
        return False


class FakeWorkflowPool:
    """Expose the asyncpg acquire contract used by workflow repositories."""

    def __init__(self, connection):
        """Store the connection used for repository calls."""
        self.connection = connection

    def acquire(self):
        """Return an asynchronous context for the stored connection."""
        return FakeAcquire(self.connection)


@pytest.mark.asyncio
async def test_claim_returns_oldest_pending_row_as_running(customer_id, workflow_id):
    """Claiming transitions a pending row to the requesting worker's RUNNING claim."""
    selected = workflow_row(workflow_id, customer_id, status="PENDING")
    claimed = workflow_row(workflow_id, customer_id, claimed_by="worker-b")
    connection = FakeConnection([selected, claimed])

    result = await claim_pending_workflow(
        FakeWorkflowPool(connection),
        ClaimWorkflowInput(
            workflow_type=WorkflowType.NEW_REGISTRATION,
            worker_id="worker-b",
        ),
    )

    assert result.id == workflow_id
    assert result.status == WorkflowStatus.RUNNING
    assert result.claimed_by == "worker-b"
    assert connection.calls == [
        (CLAIM_PENDING_SQL, ("NEW_REGISTRATION",)),
        (SET_WORKFLOW_RUNNING_SQL, (workflow_id, "worker-b")),
    ]
    assert "ORDER BY started_at ASC" in CLAIM_PENDING_SQL
    assert "FOR UPDATE SKIP LOCKED" in CLAIM_PENDING_SQL


@pytest.mark.asyncio
async def test_claim_returns_none_when_queue_is_empty():
    """An empty queue is represented by null and does not attempt an update."""
    connection = FakeConnection([None])

    result = await claim_pending_workflow(
        FakeWorkflowPool(connection),
        ClaimWorkflowInput(
            workflow_type=WorkflowType.RECIPE_GENERATION,
            worker_id="worker",
        ),
    )

    assert result is None
    assert len(connection.calls) == 1


@pytest.mark.asyncio
async def test_update_rejects_a_worker_that_does_not_own_the_row(workflow_id):
    """A database miss on the ownership predicate becomes a safe not-found error."""
    connection = FakeConnection([None])
    request = WorkflowStatusUpdate(
        workflow_id=workflow_id,
        worker_id="intruder",
        status=WorkflowStatus.SUCCESS,
    )

    with pytest.raises(NotFoundError, match="not owned"):
        await update_workflow_status(FakeWorkflowPool(connection), request)

    assert connection.calls[0][1][:2] == (workflow_id, "intruder")
    assert "WHERE id = $1 AND claimed_by = $2" in UPDATE_WORKFLOW_SQL


@pytest.mark.asyncio
async def test_update_caps_attempt_count_and_sets_terminal_status(workflow_id):
    """A terminal update returns the capped count and sets completion in SQL."""
    connection = FakeConnection(
        [{"id": workflow_id, "status": "FAILED", "attempt_count": 3, "email_status": "FAILED"}]
    )
    request = WorkflowStatusUpdate(
        workflow_id=workflow_id,
        worker_id="worker-a",
        status=WorkflowStatus.FAILED,
        increment_attempt=True,
        email_status="FAILED",
    )

    result = await update_workflow_status(FakeWorkflowPool(connection), request)

    assert result.status == WorkflowStatus.FAILED
    assert result.attempt_count == 3
    assert result.email_status.value == "FAILED"
    assert "LEAST(attempt_count + CASE WHEN $4 THEN 1 ELSE 0 END, 3)" in UPDATE_WORKFLOW_SQL
    assert "THEN CURRENT_TIMESTAMP ELSE NULL END" in UPDATE_WORKFLOW_SQL
    assert connection.calls[0][1][3:] == (True, None, "FAILED")


@pytest.mark.asyncio
async def test_update_maps_unique_index_violation_to_conflict(workflow_id):
    """An active-workflow uniqueness conflict is exposed as a safe service error."""
    connection = FakeConnection([asyncpg.UniqueViolationError("synthetic constraint")])
    request = WorkflowStatusUpdate(
        workflow_id=workflow_id,
        worker_id="worker-a",
        status=WorkflowStatus.PENDING,
    )

    with pytest.raises(ConflictError, match="conflicts with an active run"):
        await update_workflow_status(FakeWorkflowPool(connection), request)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "database_error", "expected_code"),
    [
        ("claim_select", asyncpg.ForeignKeyViolationError("SENSITIVE SQL detail"), "not_found"),
        ("claim_update", asyncpg.ConnectionFailureError("SENSITIVE connection detail"), "database_unavailable"),
        ("status_update", asyncpg.UniqueViolationError("SENSITIVE constraint detail"), "conflict"),
    ],
)
async def test_workflow_database_failures_map_without_diagnostic_leaks(
    customer_id, workflow_id, operation, database_error, expected_code
):
    """Workflow query failures map to safe errors while retaining the hidden cause."""
    selected = workflow_row(workflow_id, customer_id, status="PENDING")
    results = (
        [database_error]
        if operation == "claim_select"
        else [selected, database_error]
    )
    if operation == "status_update":
        results = [database_error]
    connection = FakeConnection(results)

    with pytest.raises(ToolServiceError) as error:
        await _run_workflow_operation(operation, connection, workflow_id)

    assert error.value.code == expected_code
    assert error.value.__cause__ is database_error
    assert "SENSITIVE" not in error.value.safe_message
    assert "SENSITIVE" not in error.value.hint


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["claim_select", "claim_update", "status_update"])
async def test_workflow_repository_propagates_unknown_sqlstate(
    customer_id, workflow_id, operation, unknown_database_error
):
    """All workflow SQL boundaries propagate an unrecognized error unchanged."""
    selected = workflow_row(workflow_id, customer_id, status="PENDING")
    results = (
        [unknown_database_error]
        if operation == "claim_select"
        else [selected, unknown_database_error]
    )
    if operation == "status_update":
        results = [unknown_database_error]
    connection = FakeConnection(results)

    with pytest.raises(type(unknown_database_error)) as error:
        await _run_workflow_operation(operation, connection, workflow_id)

    assert error.value is unknown_database_error


@pytest.mark.asyncio
async def test_missing_and_unowned_workflows_have_identical_not_found_metadata(workflow_id):
    """A missing row and an ownership-predicate miss reveal identical safe metadata."""
    errors = []
    for worker_id in ("worker-a", "synthetic-other-worker"):
        connection = FakeConnection([None])
        request = WorkflowStatusUpdate(
            workflow_id=workflow_id,
            worker_id=worker_id,
            status=WorkflowStatus.SUCCESS,
        )
        with pytest.raises(NotFoundError) as error:
            await update_workflow_status(FakeWorkflowPool(connection), request)
        errors.append(error.value)

    missing, unowned = errors
    assert (missing.code, missing.safe_message, missing.hint, missing.retryable) == (
        unowned.code,
        unowned.safe_message,
        unowned.hint,
        unowned.retryable,
    )
    assert "synthetic-other-worker" not in unowned.safe_message
    assert "synthetic-other-worker" not in unowned.hint
