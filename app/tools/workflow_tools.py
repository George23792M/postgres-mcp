"""MCP tools for claiming and updating workflows."""

from typing import Annotated
from uuid import UUID

from app.db import get_pool
from pydantic import Field
from app.repositories.workflow_repository import (
    claim_pending_workflow as claim_workflow,
)
from app.repositories.workflow_repository import (
    update_workflow_status as save_workflow_status,
)
from app.schemas import (
    ClaimWorkflowInput,
    EmailStatus,
    WorkflowStatus,
    WorkflowStatusUpdate,
    WorkflowType,
    WorkflowClaim,
    WorkflowUpdateResult,
)


async def claim_pending_workflow(
    workflow_type: WorkflowType,
    worker_id: Annotated[str, Field(min_length=1, max_length=100)],
) -> WorkflowClaim | None:
    """Atomically claim the oldest pending workflow of the requested type."""
    request = ClaimWorkflowInput(workflow_type=workflow_type, worker_id=worker_id)
    result = await claim_workflow(get_pool(), request)
    return result


async def update_workflow_status(
    workflow_id: UUID,
    worker_id: Annotated[str, Field(min_length=1, max_length=100)],
    status: WorkflowStatus,
    increment_attempt: bool = False,
    validation_errors: Annotated[str | None, Field(max_length=500)] = None,
    email_status: EmailStatus | None = None,
) -> WorkflowUpdateResult:
    """Update status, attempt count, and email state for the owning worker."""
    request = WorkflowStatusUpdate(
        workflow_id=workflow_id,
        worker_id=worker_id,
        status=status,
        increment_attempt=increment_attempt,
        validation_errors=validation_errors,
        email_status=email_status,
    )
    result = await save_workflow_status(get_pool(), request)
    return result
