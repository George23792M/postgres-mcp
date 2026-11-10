"""Request and response models for subscription workflow tools."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.schemas import StrictModel


class SubscriptionCustomer(StrictModel):
    """Active customer and selected active subscription."""

    customer_id: UUID
    first_name: str
    last_name: str
    preferred_name: str | None
    email: str
    plan_name: str


class SubscriptionClaim(StrictModel):
    """Owned registration workflow claimed for processing."""

    id: UUID
    customer_id: UUID
    claimed_by: str
    workflow_type: Literal["NEW_REGISTRATION"]
    status: Literal["RUNNING"]
    attempt_count: int


class ClaimReconciliation(StrictModel):
    """Non-personal identifiers and current state for a claim request."""

    request_id: UUID
    worker_id: str
    completed: bool
    workflow_id: UUID | None
    workflow_status: str | None
    email_status: str | None


class RegistrationCompletion(StrictModel):
    """Terminal outcome of an owned registration workflow."""

    status: Literal["SUCCESS", "FAILED"]
    email_status: Literal["SENT", "FAILED", "PENDING"]
    error_message: Annotated[str | None, Field(max_length=500)] = None

    @field_validator("error_message")
    @classmethod
    def validate_error_message(cls, value: str | None) -> str | None:
        """Reject multiline diagnostics and tracebacks."""
        if value and ("\n" in value or "\r" in value or "traceback" in value.casefold()):
            raise ValueError("Error message must be a short single-line reason")
        return value

    @model_validator(mode="after")
    def validate_delivery(self) -> "RegistrationCompletion":
        """Require confirmed email delivery before workflow success."""
        if (self.status == "SUCCESS") != (self.email_status == "SENT"):
            raise ValueError("Successful workflow requires confirmed delivery")
        return self


class WorkflowHistoryEntry(StrictModel):
    """Workflow run fields exposed by the subscription service."""

    id: UUID
    customer_id: UUID
    workflow_type: str
    status: str
    email_status: str
    attempt_count: int
    started_at: datetime
    completed_at: datetime | None
    validation_errors: str | None


class BatchRun(StrictModel):
    """Persisted batch run with its counters and completion status."""

    id: UUID
    batch_type: str
    status: Literal["RUNNING", "SUCCESS", "PARTIAL_SUCCESS", "FAILED"]
    total_customers: int
    successful_count: int
    failed_count: int
    skipped_count: int
    started_at: datetime
    completed_at: datetime | None
    error_message: str | None


class BatchCompletion(StrictModel):
    """Validated terminal status and counts for one batch."""

    status: Literal["SUCCESS", "PARTIAL_SUCCESS", "FAILED"]
    total_customers: int = Field(ge=0)
    successful_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    error_message: Annotated[str | None, Field(max_length=500)] = None

    @field_validator("error_message")
    @classmethod
    def validate_error_message(cls, value: str | None) -> str | None:
        """Reject multiline diagnostics and tracebacks."""
        if value and ("\n" in value or "\r" in value or "traceback" in value.casefold()):
            raise ValueError("Error message must be a short single-line reason")
        return value

    @model_validator(mode="after")
    def validate_counts(self) -> "BatchCompletion":
        """Require batch counters and terminal status to agree."""
        if self.successful_count + self.failed_count + self.skipped_count != self.total_customers:
            raise ValueError("Batch counts must sum to the total")
        if self.status == "SUCCESS" and self.failed_count:
            raise ValueError("Successful batch cannot contain failed workflows")
        if self.status == "PARTIAL_SUCCESS" and not self.failed_count:
            raise ValueError("Partial success requires a failed workflow")
        return self
