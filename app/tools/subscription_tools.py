"""MCP tools for subscription workflow data and batch tracking."""

from typing import Annotated
from uuid import UUID

from pydantic import Field

from app.db import get_pool
from app.repositories import subscription_repository as repository
from app.retry import with_database_retry
from app.schemas_subscription import (
    BatchCompletion,
    BatchRun,
    ClaimReconciliation,
    RegistrationCompletion,
    SubscriptionClaim,
    SubscriptionCustomer,
    WorkflowHistoryEntry,
)


async def get_subscription_customer(customer_id: UUID) -> SubscriptionCustomer:
    """Return an active customer and newest active subscription."""
    return await with_database_retry(
        lambda: repository.customer_context(get_pool(), customer_id),
        "get_subscription_customer",
    )


async def claim_registration_workflow(
    request_id: UUID,
    worker_id: Annotated[str, Field(min_length=1, max_length=100)],
    customer_id: UUID | None = None,
) -> SubscriptionClaim | None:
    """Claim a pending registration once per request ID, optionally for a customer."""
    return await with_database_retry(
        lambda: repository.claim_registration(get_pool(), request_id, worker_id, customer_id),
        "claim_registration_workflow",
    )


async def get_subscription_claim_status(request_id: UUID) -> ClaimReconciliation:
    """Look up a claim request for manual reconciliation."""
    return await with_database_retry(
        lambda: repository.claim_reconciliation(get_pool(), request_id),
        "get_subscription_claim_status",
    )


async def get_subscription_workflow_history(
    customer_id: UUID,
    workflow_type: Annotated[str | None, Field(max_length=50)] = None,
    limit: Annotated[int, Field(ge=1, le=100)] = 10,
) -> list[WorkflowHistoryEntry]:
    """Return bounded workflow history for a customer."""
    return await with_database_retry(
        lambda: repository.workflow_history(get_pool(), customer_id, workflow_type, limit),
        "get_subscription_workflow_history",
    )


async def complete_registration_workflow(
    workflow_id: UUID,
    worker_id: Annotated[str, Field(min_length=1, max_length=100)],
    result: RegistrationCompletion,
) -> WorkflowHistoryEntry:
    """Complete an owned registration workflow with replay-safe semantics."""
    return await with_database_retry(
        lambda: repository.finish_registration(get_pool(), workflow_id, worker_id, result),
        "complete_registration_workflow",
    )


async def create_subscription_batch(batch_id: UUID) -> BatchRun:
    """Create an idempotent registration batch record."""
    return await with_database_retry(
        lambda: repository.create_batch(get_pool(), batch_id),
        "create_subscription_batch",
    )


async def complete_subscription_batch(batch_id: UUID, result: BatchCompletion) -> BatchRun:
    """Persist the terminal batch status and counts."""
    return await with_database_retry(
        lambda: repository.complete_batch(get_pool(), batch_id, result),
        "complete_subscription_batch",
    )


async def get_subscription_batch_history(
    limit: Annotated[int, Field(ge=1, le=100)] = 10,
) -> list[BatchRun]:
    """Return bounded registration batch history."""
    return await with_database_retry(
        lambda: repository.batch_history(get_pool(), limit),
        "get_subscription_batch_history",
    )


async def check_database_ready() -> dict[str, bool]:
    """Confirm the server can execute a PostgreSQL query."""
    value = await with_database_retry(
        lambda: get_pool().fetchval("SELECT 1"),
        "check_database_ready",
    )
    return {"ready": value == 1}
