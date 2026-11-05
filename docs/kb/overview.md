# Overview

postgres-mcp is an authenticated MCP server (FastMCP, streamable HTTP at `/mcp`) that exposes PostgreSQL-backed tools for a smoothie-registration system: customer profile lookup, workflow queue claiming/updating, and recipe history with pgvector duplicate detection.

## Tools (5)
| Tool | Purpose |
| --- | --- |
| `get_customer_profile` | Active customer + active dietary preferences |
| `claim_pending_workflow` | Atomically claim oldest PENDING workflow of a type |
| `update_workflow_status` | Ownership-checked status update |
| `check_duplicate_recipe` | Cosine similarity search over a customer's recipes (1536-dim embeddings) |
| `save_recipe` | Idempotent upsert per (customer, day) |

## Users
Inferred: AI agents/workers (e.g. recipe-generation and registration workers) that connect as MCP clients using a shared bearer token. README states the token does not identify individual agents.

## Limitations (from README)
No stale-claim recovery for crashed workers; no per-agent authorization; server never runs migrations.

Sources: README.md, app/server.py
Verified: 2026-11-05
