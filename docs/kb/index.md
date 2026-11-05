Last scan: 2026-11-05
Commit: ac9830076d891a4b566780a4c6ae93cb6ccda446

# postgres-mcp Knowledge Base

Stack: Python 3.12, FastMCP (official `mcp` SDK), asyncpg, pydantic / pydantic-settings, loguru, pytest. No matching `~/.copilot/standards` folder was consulted (Inferred: none applies to MCP servers); layering is tools -> repositories -> asyncpg pool.

## Table of contents
- [overview.md](overview.md): purpose, features, users
- [architecture.md](architecture.md): layers, data flow, entry point, diagram
- [design-patterns.md](design-patterns.md)
- [infrastructure.md](infrastructure.md): config/env vars, run, auth, CI/CD status
- [database.md](database.md): tables, SQL, migration 002
- [components/server.md](components/server.md)
- [components/tools-and-repositories.md](components/tools-and-repositories.md)
- [components/config-db-schemas.md](components/config-db-schemas.md)
- [learnings.md](learnings.md): reflection log

## Scanned areas
main.py, app/*, app/tools/*, app/repositories/*, pyproject.toml, .env.example (names only), README.md, qeuries.sql, restart.ps1, tests/ (file list and test counts only), .ai/postmortem/lessons.md.

## Known gaps
- Test bodies were not read (only file list and counts).
- Base schema (`smoothie-registration/create-tables.sql`) is external; column types of base tables are Inferred from queries/README.
- No CI/CD, Docker, or deployment config found in the repo.
- `.ai/plans/*.yaml` and `.vscode/` not read.
- `requirements.txt` and `uv.lock` not read.
