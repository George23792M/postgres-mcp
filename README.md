# Postgres MCP server

An authenticated MCP server exposing customer profile, workflow queue, and
recipe-history tools backed by PostgreSQL and `asyncpg`. It uses the official
Python MCP SDK's FastMCP implementation with the streamable HTTP transport.

## Requirements and database setup

- Python 3.12 or newer. Install dependencies with `pip` or `uv`.
- PostgreSQL with the `pgvector` extension installed and available.
- The base schema from `smoothie-registration/create-tables.sql`.
- Migration 002 from this repository's `qeuries.sql`, applied after the base
  schema. The migration adds the active-preference, workflow-claim, and
  per-customer/day uniqueness columns and indexes used by the tools.

The server does not create extensions or run migrations. Apply schema changes
with a database administrator before starting the server. Use a dedicated
database role for this service: grant only the needed `SELECT` access on
`customers` and `customer_preferences`, `SELECT`/`UPDATE` on `workflow_runs`,
and `SELECT`/`INSERT`/`UPDATE` on `recipe_history`. Do not grant DDL, delete, or
access to unrelated tables. Use row-level security or a trusted gateway if the
service must restrict access to particular customers; the shared MCP bearer
token does not identify individual agents.

## Configure and run

From the repository root, copy `.env.example` to `.env` and configure the
required values using your secret manager. Keep actual credentials in `.env`
and never add them to documentation or source control.

With pip:

```powershell
python -m pip install -r requirements.txt
python main.py
```

Or, with `uv`:

```powershell
uv sync
uv run python main.py
```

The server binds to `127.0.0.1:8000` by default and serves MCP at
`http://127.0.0.1:8000/mcp`. A valid `MCP_AUTH_TOKEN` (at least 32 characters)
and database credentials are required at startup. Never commit `.env` or put
real credentials in documentation. For network use, bind only behind a
trusted TLS-terminating reverse proxy, provision the shared token securely,
and set `MCP_ALLOWED_HOSTS` to a JSON array containing the expected
`host:port` values, for example `["mcp.example.internal:8000"]`.

| Environment variable | Required | Default / purpose |
| --- | --- | --- |
| `DB_USER` | Yes | PostgreSQL service-role username. |
| `DB_PASSWORD` | Yes | PostgreSQL service-role password. |
| `DB_HOST` | Yes | PostgreSQL hostname or address. |
| `DB_PORT` | Yes | PostgreSQL port (1-65535). |
| `DB_NAME` | Yes | Database containing the required schema. |
| `MCP_AUTH_TOKEN` | Yes | Shared bearer token; at least 32 characters. |
| `MCP_HOST` | No | Bind address; defaults to `127.0.0.1`. |
| `MCP_PORT` | No | HTTP port; defaults to `8000`. |
| `MCP_ALLOWED_HOSTS` | No | JSON array of allowed request `host:port` values; localhost values are used when omitted. |
| `LOG_LEVEL` | No | Loguru level; defaults to `INFO`. |
| `DB_POOL_MIN_SIZE` | No | Minimum asyncpg pool size; defaults to `1`. |
| `DB_POOL_MAX_SIZE` | No | Maximum asyncpg pool size; defaults to `10`. |
| `DB_COMMAND_TIMEOUT` | No | Query timeout in seconds; defaults to `30`. |

## Connect an MCP client

Set the client URL to `http://host:port/mcp` and send an
`Authorization: Bearer <MCP_AUTH_TOKEN>` header on HTTP requests. With the
Python MCP SDK, supply that header through an `httpx.AsyncClient`:

```python
import os

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def list_server_tools() -> None:
    """Connect to the server and list its registered MCP tools."""
    headers = {"Authorization": f"Bearer {os.environ['MCP_AUTH_TOKEN']}"}
    async with httpx.AsyncClient(headers=headers) as http_client:
        async with streamable_http_client(
            "http://127.0.0.1:8000/mcp",
            http_client=http_client,
        ) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.list_tools()
                print([tool.name for tool in result.tools])
```

## Tool reference

All IDs are UUIDs. Invalid arguments are rejected before database access.
Expected not-found, ownership, or conflict conditions are returned as
client-safe tool errors. Unexpected failures return a generic message with a
reference ID; logs contain the reference and error type, not recipe text,
embeddings, credentials, or database connection strings.

| Tool | Inputs | Result |
| --- | --- | --- |
| `get_customer_profile` | `customer_id` | Active customer identity and active dietary preferences. An unknown or inactive customer is not found; no active preferences returns empty lists. |
| `claim_pending_workflow` | `workflow_type` (`NEW_REGISTRATION` or `RECIPE_GENERATION`), `worker_id` (1–100 chars) | Oldest pending workflow claimed atomically as `RUNNING`, or `null` when the queue is empty. Concurrent workers skip rows already being claimed. |
| `update_workflow_status` | `workflow_id`, `worker_id`, `status` (`PENDING`, `RUNNING`, `SUCCESS`, `FAILED`), optional `increment_attempt`, single-line `validation_errors` (max 500 chars), optional `email_status` (`PENDING`, `SENT`, `FAILED`) | Updated status, attempt count (capped at 3), and email status. Only the worker recorded in `claimed_by` can update the row. `completed_at` is set for `SUCCESS`/`FAILED` and cleared otherwise. |
| `check_duplicate_recipe` | `customer_id`, `embedding` (exactly 1536 finite numbers), optional `threshold` (exclusive 0, up to 1; default `0.90`), optional `limit` (1–20; default `5`) | `is_duplicate` and closest matching recipes (`recipe_name`, `day_number`, `similarity`), scoped to that customer. |
| `save_recipe` | `customer_id`, `recipe_name` (1–255 chars), `day_number` (at least 1), `ingredients` (up to 12,000 chars), `instructions` (up to 20,000 chars), `embedding` (exactly 1536 finite numbers), optional `calories` (0–10,000) | Recipe UUID. Repeating a save for the same customer/day updates the existing row. |

Example `call_tool` arguments:

```python
await session.call_tool(
    "get_customer_profile",
    {"customer_id": "00000000-0000-0000-0000-000000000001"},
)
await session.call_tool(
    "claim_pending_workflow",
    {"workflow_type": "RECIPE_GENERATION", "worker_id": "recipe-worker-1"},
)
await session.call_tool(
    "update_workflow_status",
    {
        "workflow_id": "00000000-0000-0000-0000-000000000002",
        "worker_id": "recipe-worker-1",
        "status": "SUCCESS",
    },
)
embedding = [0.0] * 1536
await session.call_tool(
    "check_duplicate_recipe",
    {"customer_id": "00000000-0000-0000-0000-000000000001", "embedding": embedding},
)
await session.call_tool(
    "save_recipe",
    {
        "customer_id": "00000000-0000-0000-0000-000000000001",
        "recipe_name": "Berry breakfast smoothie",
        "day_number": 1,
        "ingredients": "berries, yogurt, oats",
        "instructions": "Blend until smooth.",
        "embedding": embedding,
    },
)
```

`claim_pending_workflow` has no stale-claim recovery; a crashed worker can
leave a workflow in `RUNNING`. Recovery and per-agent authorization are outside
the current server scope.