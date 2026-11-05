"""Validation coverage for MCP tool input and output models."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from app.schemas import (
    ClaimWorkflowInput,
    RecipeDuplicateInput,
    RecipeSaveInput,
    WorkflowClaim,
    WorkflowStatusUpdate,
    WorkflowType,
)


def test_recipe_save_accepts_valid_bounded_payload(customer_id, embedding):
    """A valid recipe with a 1536-component embedding is accepted."""
    result = RecipeSaveInput(
        customer_id=customer_id,
        recipe_name=" Berry blend ",
        day_number=1,
        ingredients="berries and oats",
        instructions="Blend until smooth.",
        embedding=embedding,
        calories=0,
    )

    assert result.recipe_name == "Berry blend"
    assert result.day_number == 1
    assert result.calories == 0
    assert len(result.embedding) == 1536


@pytest.mark.parametrize("length", [0, 1535, 1537])
def test_embedding_rejects_empty_or_wrong_dimension(length, customer_id):
    """Embeddings must contain exactly 1536 values."""
    with pytest.raises(ValidationError):
        RecipeDuplicateInput(customer_id=customer_id, embedding=[0.0] * length)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), True, "0.5"])
def test_embedding_rejects_non_finite_or_non_numeric_values(value, customer_id):
    """Embedding values must be finite real numbers, not booleans or text."""
    with pytest.raises(ValidationError):
        RecipeDuplicateInput(customer_id=customer_id, embedding=[value] + [0.0] * 1535)


def test_recipe_duplicate_rejects_threshold_and_limit_boundaries(customer_id, embedding):
    """Similarity threshold and result limit enforce their documented bounds."""
    valid_maximums = RecipeDuplicateInput(
        customer_id=customer_id,
        embedding=embedding,
        threshold=1,
        limit=20,
    )
    assert valid_maximums.threshold == 1
    assert valid_maximums.limit == 20

    with pytest.raises(ValidationError):
        RecipeDuplicateInput(customer_id=customer_id, embedding=embedding, threshold=0)
    with pytest.raises(ValidationError):
        RecipeDuplicateInput(customer_id=customer_id, embedding=embedding, threshold=1.01)
    with pytest.raises(ValidationError):
        RecipeDuplicateInput(customer_id=customer_id, embedding=embedding, limit=21)


def test_recipe_save_rejects_oversized_content_and_extra_fields(customer_id, embedding):
    """Recipe text is bounded and undeclared agent fields are forbidden."""
    values = {
        "customer_id": customer_id,
        "recipe_name": "Smoothie",
        "day_number": 1,
        "ingredients": "x" * 12001,
        "instructions": "Blend.",
        "embedding": embedding,
    }

    with pytest.raises(ValidationError):
        RecipeSaveInput(**values)
    values["ingredients"] = "berries"
    values["admin"] = True
    with pytest.raises(ValidationError):
        RecipeSaveInput(**values)


def test_recipe_save_rejects_empty_text_and_out_of_range_numbers(customer_id, embedding):
    """Recipe text is required and day and calorie values stay within bounds."""
    required = {
        "customer_id": customer_id,
        "recipe_name": " ",
        "day_number": 0,
        "ingredients": "",
        "instructions": " ",
        "embedding": embedding,
    }

    with pytest.raises(ValidationError):
        RecipeSaveInput(**required)
    required.update(recipe_name="Berry blend", day_number=1, ingredients="berries", instructions="Blend.")
    required["calories"] = 10001
    with pytest.raises(ValidationError):
        RecipeSaveInput(**required)


def test_workflow_inputs_reject_invalid_enum_ids_and_worker_bounds():
    """Workflow identifiers, types, and bounded worker names are validated."""
    with pytest.raises(ValidationError):
        ClaimWorkflowInput(workflow_type="DELETE_ALL", worker_id="worker")
    with pytest.raises(ValidationError):
        ClaimWorkflowInput(workflow_type=WorkflowType.NEW_REGISTRATION, worker_id="")
    with pytest.raises(ValidationError):
        WorkflowStatusUpdate(
            workflow_id="not-a-uuid",
            worker_id="worker",
            status="SUCCESS",
        )
    with pytest.raises(ValidationError):
        WorkflowStatusUpdate(
            workflow_id=UUID("00000000-0000-0000-0000-000000000203"),
            worker_id="worker",
            status="DELETE",
        )
    with pytest.raises(ValidationError):
        WorkflowStatusUpdate(
            workflow_id=UUID("00000000-0000-0000-0000-000000000203"),
            worker_id="worker",
            status="SUCCESS",
            unexpected="field",
        )


@pytest.mark.parametrize(
    "reason",
    ["Traceback starts here", "traceback starts here", "first\nsecond", "first\rsecond"],
)
def test_workflow_update_rejects_multiline_diagnostics(reason):
    """Failure details cannot contain tracebacks or multiple lines."""
    with pytest.raises(ValidationError):
        WorkflowStatusUpdate(
            workflow_id=UUID("00000000-0000-0000-0000-000000000203"),
            worker_id="worker",
            status="FAILED",
            validation_errors=reason,
        )


def test_workflow_output_rejects_attempt_count_above_cap():
    """Workflow claim output rejects a count above the three-attempt maximum."""
    with pytest.raises(ValidationError):
        WorkflowClaim(
            id=UUID("00000000-0000-0000-0000-000000000203"),
            customer_id=UUID("00000000-0000-0000-0000-000000000204"),
            status="RUNNING",
            attempt_count=4,
            email_status="PENDING",
            workflow_type="NEW_REGISTRATION",
            started_at="2026-01-01T00:00:00Z",
            claimed_by="worker",
        )
