"""Authenticated FastMCP server construction and lifespan management."""

import hmac
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from functools import partial, wraps
from typing import Any
from uuid import uuid4

from loguru import logger
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import Settings, get_settings
from app.db import close_pool, create_pool
from app.errors import InvalidInputError, ToolServiceError
from app.retry import RetryConfig, set_retry_config
from app.tools.customer_tools import get_customer_profile
from app.tools.email_tools import get_active_email_template
from app.tools.recipe_tools import check_duplicate_recipe, save_recipe
from app.tools.subscription_tools import (
    check_database_ready, claim_registration_workflow, complete_registration_workflow,
    complete_subscription_batch,
    create_subscription_batch, get_subscription_batch_history,
    get_subscription_claim_status, get_subscription_customer, get_subscription_workflow_history,
)
from app.tools.workflow_tools import claim_pending_workflow, update_workflow_status

ToolFunction = Callable[..., Awaitable[Any]]


class BearerAuthMiddleware:
    """Require the configured bearer token for every HTTP request."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        """Store the downstream ASGI application and expected token."""
        self.app = app
        self.token = token

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """Reject unauthorized requests before they reach FastMCP."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive)
        if not self._is_authorized(request.headers.get("authorization", "")):
            response = JSONResponse(
                {"error": "Unauthorized"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)

    def _is_authorized(self, authorization: str) -> bool:
        """Compare a supplied bearer token in constant time."""
        scheme, separator, supplied_token = authorization.partition(" ")
        if not separator or scheme.casefold() != "bearer" or len(supplied_token) > 4096:
            return False
        return hmac.compare_digest(
            self.token.encode("utf-8"),
            supplied_token.encode("utf-8"),
        )


@asynccontextmanager
async def lifespan(
    server: FastMCP,
    settings: Settings | None = None,
) -> AsyncIterator[dict[str, object]]:
    """Initialize retry config and database pool at startup."""
    config = settings or get_settings()
    retry_config = RetryConfig.from_settings(config)
    set_retry_config(retry_config)
    await create_pool(config)
    try:
        yield {}
    finally:
        await close_pool()


def _format_service_error(error: ToolServiceError) -> str:
    """Render stable safe metadata for expected MCP tool failures."""
    return (
        f"code={error.code}; message={error.safe_message}; "
        f"hint={error.hint}; retryable={str(error.retryable).lower()}"
    )


def _safe_tool(tool: ToolFunction) -> ToolFunction:
    """Translate expected failures and mask unexpected tool exceptions."""

    @wraps(tool)
    async def wrapped(*args: Any, **kwargs: Any) -> Any:
        """Execute a tool with client-safe exception handling."""
        try:
            return await tool(*args, **kwargs)
        except ToolServiceError as error:
            raise ToolError(_format_service_error(error)) from error
        except ValidationError as error:
            invalid_input = InvalidInputError()
            raise ToolError(_format_service_error(invalid_input)) from error
        except Exception as error:
            reference = uuid4().hex
            logger.error(
                "Unexpected tool failure reference={} type={}",
                reference,
                type(error).__name__,
            )
            raise ToolError(f"Request failed; reference={reference}") from None

    return wrapped


class AuthenticatedFastMCP(FastMCP):
    """FastMCP server that installs bearer authentication on HTTP apps."""

    def __init__(self, bearer_token: str, **kwargs: Any) -> None:
        """Initialize FastMCP and retain the shared bearer token."""
        super().__init__(**kwargs)
        self._bearer_token = bearer_token

    def streamable_http_app(self) -> Starlette:
        """Build the streamable HTTP app with bearer authentication."""
        app = super().streamable_http_app()
        app.add_middleware(BearerAuthMiddleware, token=self._bearer_token)
        return app

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Mask FastMCP argument-validation errors before they reach clients."""
        try:
            return await super().call_tool(name, arguments)
        except ToolError as error:
            if isinstance(error.__cause__, ValidationError):
                raise ToolError(_format_service_error(InvalidInputError())) from None
            raise


def create_server(settings: Settings | None = None) -> AuthenticatedFastMCP:
    """Create the configured server and register its database tools."""
    config = settings or get_settings()
    logger.remove()
    logger.add(sys.stderr, level=config.log_level)
    allowed_hosts = config.mcp_allowed_hosts or [
        f"{config.mcp_host}:{config.mcp_port}",
        f"localhost:{config.mcp_port}",
        f"127.0.0.1:{config.mcp_port}",
    ]
    server = AuthenticatedFastMCP(
        name="postgres-mcp",
        host=config.mcp_host,
        port=config.mcp_port,
        log_level=config.log_level,
        streamable_http_path="/mcp",
        lifespan=partial(lifespan, settings=config),
        transport_security=TransportSecuritySettings(allowed_hosts=allowed_hosts),
        bearer_token=config.mcp_auth_token.get_secret_value(),
    )
    _register_tools(server)
    return server


def _register_tools(server: FastMCP) -> None:
    """Register database tools with concise agent-facing descriptions."""
    tools = (
        (
            get_customer_profile,
            "Return an active customer's identity and active dietary preferences.",
        ),
        (
            claim_pending_workflow,
            "Atomically claim the oldest pending workflow of a requested type.",
        ),
        (
            update_workflow_status,
            "Update a workflow only when the caller owns its claim.",
        ),
        (check_duplicate_recipe, "Find similar recipes in this customer's history."),
        (save_recipe, "Idempotently save a recipe and its caller-provided embedding."),
        (get_subscription_customer, "Get an active customer and latest active subscription."),
        (claim_registration_workflow, "Claim a registration workflow idempotently."),
        (get_subscription_claim_status, "Look up a claim request for manual reconciliation."),
        (complete_registration_workflow, "Complete an owned registration workflow."),
        (get_subscription_workflow_history, "List a customer's workflow history."),
        (create_subscription_batch, "Create a registration batch."),
        (complete_subscription_batch, "Complete a registration batch."),
        (get_subscription_batch_history, "List registration batch history."),
        (check_database_ready, "Check PostgreSQL readiness."),
        (get_active_email_template, "Get the active email template for a given name."),
    )
    for tool, description in tools:
        server.tool(description=description)(_safe_tool(tool))



