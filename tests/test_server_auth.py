"""Authentication, tool registration, and safe error mapping tests."""

import httpx
import pytest
from loguru import logger
from mcp.server.fastmcp.exceptions import ToolError

from app.errors import DatabaseUnavailableError, InvalidInputError, NotFoundError
from app.server import BearerAuthMiddleware, _safe_tool, create_server


@pytest.mark.asyncio
async def test_bearer_auth_middleware_rejects_missing_and_invalid_tokens(test_settings):
    """Requests without the exact configured bearer token receive HTTP 401."""
    server = create_server(test_settings)
    app = server.streamable_http_app()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        missing = await client.post("/mcp")
        invalid = await client.post(
            "/mcp",
            headers={"Authorization": "Bearer synthetic-wrong-token"},
        )

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert missing.headers["www-authenticate"] == "Bearer"
    assert "Unauthorized" in missing.text
    assert test_settings.mcp_auth_token.get_secret_value() not in missing.text


def test_bearer_auth_compares_scheme_case_insensitively_and_bounds_header(test_settings):
    """Bearer scheme casing is accepted while malformed and oversized values fail."""
    middleware = BearerAuthMiddleware(
        app=None,
        token=test_settings.mcp_auth_token.get_secret_value(),
    )

    assert middleware._is_authorized(
        f"bEaReR {test_settings.mcp_auth_token.get_secret_value()}"
    )
    assert not middleware._is_authorized("Basic credentials")
    assert not middleware._is_authorized("Bearer " + "x" * 4097)
    assert not middleware._is_authorized("Bearer")


@pytest.mark.asyncio
async def test_server_registers_expected_tools(test_settings):
    """The MCP server exposes its named tools and their input schemas."""
    server = create_server(test_settings)

    tools = await server.list_tools()

    assert {tool.name for tool in tools} == {
        "get_customer_profile",
        "claim_pending_workflow",
        "update_workflow_status",
        "check_duplicate_recipe",
        "save_recipe",
        "get_subscription_customer",
        "claim_registration_workflow",
        "get_subscription_claim_status",
        "complete_registration_workflow",
        "get_subscription_workflow_history",
        "create_subscription_batch",
        "complete_subscription_batch",
        "get_subscription_batch_history",
        "check_database_ready",
    }
    assert all(tool.inputSchema.get("type") == "object" for tool in tools)
    assert {tool.name: tool.description for tool in tools}["save_recipe"]


@pytest.mark.asyncio
async def test_safe_tool_preserves_successful_return_values():
    """Successful wrapped tools return their original result unchanged."""
    async def successful_tool():
        """Return a deterministic result as a normal tool would."""
        return {"status": "ok", "count": 2}

    assert await _safe_tool(successful_tool)() == {"status": "ok", "count": 2}


@pytest.mark.asyncio
async def test_safe_tool_formats_expected_service_error_metadata():
    """Expected service errors render all stable fields instead of legacy prose."""
    async def missing_customer():
        """Raise a service error containing unsafe legacy text."""
        raise NotFoundError("synthetic private customer details")

    with pytest.raises(ToolError) as error:
        await _safe_tool(missing_customer)()

    rendered = str(error.value)
    assert rendered == (
        "code=not_found; message=The requested resource was not found.; "
        "hint=Verify the identifier and your access to the requested resource.; "
        "retryable=false"
    )
    assert "synthetic private customer details" not in rendered


@pytest.mark.asyncio
async def test_safe_tool_marks_database_unavailable_retryable():
    """A transient availability error renders its code and retryable status."""
    async def database_unavailable():
        """Raise the expected temporary database error."""
        raise DatabaseUnavailableError()

    with pytest.raises(ToolError) as error:
        await _safe_tool(database_unavailable)()

    assert "code=database_unavailable;" in str(error.value)
    assert "retryable=true" in str(error.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "payload"),
    [
        ("customer_id", "'; DROP TABLE customers; --"),
        ("customer_id", "synthetic-secret-value-do-not-reflect"),
        ("ingredients", "oversized-synthetic-payload-" + "x" * 12000),
        ("customer_id", "not-a-uuid"),
    ],
)
async def test_safe_tool_masks_validation_values_and_internals(
    field, payload, customer_id, embedding
):
    """Validation errors reveal neither hostile values nor Pydantic diagnostics."""
    from app.schemas import RecipeSaveInput

    values = {
        "customer_id": customer_id,
        "recipe_name": "Berry blend",
        "day_number": 1,
        "ingredients": "berries",
        "instructions": "Blend.",
        "embedding": embedding,
    }
    values[field] = payload

    async def invalid_tool():
        """Trigger real Pydantic validation inside the wrapped tool."""
        RecipeSaveInput(**values)

    with pytest.raises(ToolError) as error:
        await _safe_tool(invalid_tool)()

    rendered = str(error.value)
    assert rendered.startswith("code=invalid_input; message=The tool input is invalid.;")
    assert rendered.endswith("retryable=false")
    assert payload not in rendered
    assert "ValidationError" not in rendered
    assert "input_value" not in rendered
    assert "Traceback" not in rendered


@pytest.mark.asyncio
async def test_safe_tool_masks_unexpected_details_and_logs_only_reference_and_type():
    """Unexpected error messages and payloads stay out of responses and logs."""
    import io

    output = io.StringIO()
    sink_id = logger.add(output, format="{message}")
    secret = "synthetic-db-password-and-SQL-SELECT-secret"

    async def unexpected_failure(payload):
        """Raise an unexpected failure containing synthetic sensitive details."""
        raise RuntimeError(f"{secret}; request={payload}")

    try:
        with pytest.raises(ToolError) as error:
            await _safe_tool(unexpected_failure)(secret)
    finally:
        logger.remove(sink_id)

    rendered = str(error.value)
    logged = output.getvalue()
    assert rendered.startswith("Request failed; reference=")
    reference = rendered.split("reference=", 1)[1]
    assert reference and len(reference) == 32
    assert reference in logged
    assert "RuntimeError" in logged
    assert secret not in rendered
    assert secret not in logged
    assert "request=" not in logged
    assert "Traceback" not in rendered


@pytest.mark.asyncio
async def test_safe_tool_translates_invalid_input_error_without_retry():
    """The explicit invalid-input category is rendered as non-retryable."""
    async def invalid_request():
        """Raise an expected safe invalid-input service error."""
        raise InvalidInputError("attacker-controlled detail")

    with pytest.raises(ToolError) as error:
        await _safe_tool(invalid_request)()

    assert "code=invalid_input;" in str(error.value)
    assert "retryable=false" in str(error.value)
    assert "attacker-controlled detail" not in str(error.value)


@pytest.mark.asyncio
async def test_call_tool_masks_pre_execution_validation_errors(test_settings, monkeypatch):
    """FastMCP validation must not expose the supplied argument in errors."""
    server = create_server(test_settings)
    monkeypatch.setattr(server, "get_context", lambda: None)
    invalid_id = "synthetic-invalid-uuid-payload"

    with pytest.raises(ToolError) as error:
        await server.call_tool("get_customer_profile", {"customer_id": invalid_id})

    assert str(error.value).startswith("code=invalid_input;")
    assert "retryable=false" in str(error.value)
    assert invalid_id not in str(error.value)


@pytest.mark.asyncio
async def test_safe_tool_masks_unexpected_exception_details():
    """Unexpected failures expose a reference but not database exception details."""
    async def database_failure():
        """Raise an internal error that must not reach the client."""
        raise RuntimeError("synthetic internal database detail")

    with pytest.raises(ToolError) as error:
        await _safe_tool(database_failure)()

    assert "reference=" in str(error.value)
    assert "synthetic internal database detail" not in str(error.value)


def test_readme_documents_the_safe_structured_error_contract():
    """The README contract remains aligned with rendered errors regardless of wrapping."""
    import re
    from pathlib import Path

    readme = Path(__file__).resolve().parents[1] / "README.md"
    text = " ".join(readme.read_text(encoding="utf-8").split())

    for phrase in (
        "code=<code>; message=<message>; hint=<hint>; retryable=<true|false>",
        "not_found",
        "conflict",
        "database_unavailable",
        "invalid_input",
        "reference ID",
        "bounded retry policy",
        "same code and client-visible text",
    ):
        assert re.search(re.escape(phrase), text, flags=re.IGNORECASE), phrase
