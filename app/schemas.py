"""Validated request and response models for the MCP tools."""

import math
from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    """Base model that rejects undeclared fields and trims text inputs."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class WorkflowType(StrEnum):
    """Workflow categories supported by the registration database."""

    NEW_REGISTRATION = "NEW_REGISTRATION"
    RECIPE_GENERATION = "RECIPE_GENERATION"


class WorkflowStatus(StrEnum):
    """Valid workflow states persisted by the worker tools."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class EmailStatus(StrEnum):
    """Valid email delivery states stored on a workflow run."""

    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"


class CustomerProfileInput(StrictModel):
    """Input identifying the customer whose profile is requested."""

    customer_id: UUID


class DietaryConstraints(StrictModel):
    """One active preference row and its derived dietary restrictions."""

    profile_name: Annotated[str, Field(min_length=1, max_length=100)]
    days: int = Field(ge=1, le=30)
    max_calories: int = Field(ge=1, le=10000)
    nut_free: bool
    gluten_free: bool
    dairy_free: bool
    soy_free: bool
    constraints: list[str]


class CustomerProfile(StrictModel):
    """Customer identity and currently active dietary preferences."""

    id: UUID
    first_name: Annotated[str, Field(min_length=1, max_length=100)]
    middle_name: Annotated[str | None, Field(max_length=100)] = None
    last_name: Annotated[str, Field(min_length=1, max_length=100)]
    preferred_name: Annotated[str | None, Field(max_length=100)] = None
    email: Annotated[str, Field(min_length=3, max_length=255)]
    is_active: bool
    dietary_preferences: list[DietaryConstraints]
    constraints: list[str]


class ClaimWorkflowInput(StrictModel):
    """Validated request to claim the next workflow of a given type."""

    workflow_type: WorkflowType
    worker_id: Annotated[str, Field(min_length=1, max_length=100)]


class WorkflowClaim(StrictModel):
    """Workflow row returned after it is atomically claimed."""

    id: UUID
    customer_id: UUID
    status: WorkflowStatus
    attempt_count: int = Field(ge=0, le=3)
    validation_errors: Annotated[str | None, Field(max_length=500)] = None
    email_status: EmailStatus
    workflow_type: WorkflowType
    started_at: datetime
    claimed_by: Annotated[str, Field(min_length=1, max_length=100)]


class WorkflowStatusUpdate(StrictModel):
    """Ownership-checked request to update a claimed workflow."""

    workflow_id: UUID
    worker_id: Annotated[str, Field(min_length=1, max_length=100)]
    status: WorkflowStatus
    increment_attempt: bool = False
    validation_errors: Annotated[str | None, Field(max_length=500)] = None
    email_status: EmailStatus | None = None

    @field_validator("validation_errors")
    @classmethod
    def validate_failure_reason(cls, value: str | None) -> str | None:
        """Reject multiline diagnostics rather than persisting stack traces."""
        if value is not None and (
            "\n" in value or "\r" in value or "traceback" in value.casefold()
        ):
            raise ValueError("Validation errors must be a short single-line reason")
        return value


class WorkflowUpdateResult(StrictModel):
    """Status and attempt count returned after a workflow update."""

    id: UUID
    status: WorkflowStatus
    attempt_count: int = Field(ge=0, le=3)
    email_status: EmailStatus


class EmbeddingInput(StrictModel):
    """Base input requiring a finite 1536-dimensional embedding."""

    embedding: list[float] = Field(min_length=1536, max_length=1536)

    @field_validator("embedding", mode="before")
    @classmethod
    def validate_embedding_types(cls, values: object) -> object:
        """Reject booleans and non-numeric components before coercion."""
        if not isinstance(values, list) or any(
            isinstance(value, bool) or not isinstance(value, (int, float))
            for value in values
        ):
            raise ValueError("Embedding values must be finite numbers")
        return values

    @field_validator("embedding")
    @classmethod
    def validate_embedding(cls, values: list[float]) -> list[float]:
        """Reject NaN and infinite vector components."""
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Embedding values must be finite")
        return values


class RecipeDuplicateInput(EmbeddingInput):
    """Input for searching a customer's recipe history for similar items."""

    customer_id: UUID
    threshold: float = Field(default=0.90, gt=0, le=1)
    limit: int = Field(default=5, ge=1, le=20)


class RecipeMatch(StrictModel):
    """Recipe candidate and its cosine similarity score."""

    recipe_name: Annotated[str, Field(min_length=1, max_length=255)]
    day_number: int = Field(ge=1)
    similarity: float = Field(ge=-1, le=1)


class DuplicateCheckResult(StrictModel):
    """Duplicate-check outcome and the most similar recipe candidates."""

    is_duplicate: bool
    matches: list[RecipeMatch]


class RecipeSaveInput(EmbeddingInput):
    """Validated recipe content and caller-provided embedding."""

    customer_id: UUID
    recipe_name: Annotated[str, Field(min_length=1, max_length=255)]
    day_number: int = Field(ge=1)
    ingredients: Annotated[str, Field(min_length=1, max_length=12000)]
    instructions: Annotated[str, Field(min_length=1, max_length=20000)]
    calories: int | None = Field(default=None, ge=0, le=10000)


class RecipeSaveResult(StrictModel):
    """Identifier of a newly inserted or idempotently updated recipe."""

    id: UUID
