# Component: server (`app/server.py`)

- `create_server(settings=None)`: configures loguru (stderr), builds `AuthenticatedFastMCP` named "postgres-mcp", registers tools.
- `_register_tools`: registers exactly five tools, each wrapped by `_safe_tool`.
- `AuthenticatedFastMCP.streamable_http_app`: adds `BearerAuthMiddleware`; 401 with `WWW-Authenticate: Bearer` on failure; non-HTTP scopes pass through.
- `lifespan`: `create_pool` then `close_pool`.
- Tested by `tests/test_server_auth.py` (contents not read).

Sources: app/server.py, main.py
Verified: 2026-11-05
