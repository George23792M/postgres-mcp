"""Authentication, tool registration, and safe error mapping tests."""

import httpx
import pytest
from mcp.server.fastmcp.exceptions import ToolError

from app.errors import NotFoundError
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
async def test_server_registers_exactly_five_expected_tools(test_settings):
    """The MCP server exposes all five named tools and their input schemas."""
    server = create_server(test_settings)

    tools = await server.list_tools()

    assert {tool.name for tool in tools} == {
        "get_customer_profile",
        "claim_pending_workflow",
        "update_workflow_status",
        "check_duplicate_recipe",
        "save_recipe",
    }
    assert all(tool.inputSchema.get("type") == "object" for tool in tools)
    assert {tool.name: tool.description for tool in tools}["save_recipe"]


@pytest.mark.asyncio
async def test_safe_tool_exposes_expected_service_error_message():
    """Expected service errors remain clear and client-safe."""
    async def missing_customer():
        """Raise the service error to exercise safe error translation."""
        raise NotFoundError("Customer not found")

    with pytest.raises(ToolError, match="Customer not found"):
        await _safe_tool(missing_customer)()


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
