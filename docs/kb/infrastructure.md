# Infrastructure

- Hosting: none defined. Runs locally via `python main.py`, `uv run python main.py`, or `restart.ps1` (stops all `python` processes, then `uv run main.py`; note it kills every Python process).
- CI/CD, Docker, cloud services: none found in repo (no `.github`, Dockerfile, compose).
- Transport: streamable HTTP, path `/mcp`, default bind 127.0.0.1:8000. DNS-rebinding protection via `TransportSecuritySettings(allowed_hosts=...)`; defaults to host:port, localhost:port, 127.0.0.1:port.
- Auth: shared bearer token (`MCP_AUTH_TOKEN`, min 32 chars); README recommends TLS-terminating reverse proxy.
- Third-party APIs: none. Embeddings are caller-supplied.
- Dependencies: asyncpg, loguru, mcp[cli] (>=1.9,<2), pydantic-settings; dev: pytest, pytest-asyncio (`pyproject.toml`).
- Python >=3.12 (`.python-version` present, not read).

## Environment variables (names only; loaded from env or `.env`)
Required: `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `MCP_AUTH_TOKEN`.
Optional: `MCP_HOST`, `MCP_PORT`, `MCP_ALLOWED_HOSTS` (JSON list), `LOG_LEVEL`, `DB_POOL_MIN_SIZE`, `DB_POOL_MAX_SIZE`, `DB_COMMAND_TIMEOUT`.
Validation in `app/config.py:Settings` (pool max >= min, port ranges, timeout <=300).

Sources: README.md, app/config.py, app/server.py, .env.example, restart.ps1, pyproject.toml
Verified: 2026-11-05
