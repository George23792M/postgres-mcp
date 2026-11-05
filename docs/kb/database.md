# Database

- Engine: PostgreSQL with `pgvector` extension. Driver: asyncpg (no ORM, raw parameterized SQL).
- Base schema is external (`smoothie-registration/create-tables.sql`, per README). Server does not migrate.
- Migration 002 in `qeuries.sql` (name misspelled in repo): adds `workflow_runs.updt_ts`, `claimed_by`; makes `completed_at` nullable; index `idx_workflow_claim(workflow_type,status,started_at)`; partial unique `uq_workflow_active(customer_id, workflow_type)` where status in PENDING/RUNNING/SUCCESS; `uq_recipe_customer_day` on `recipe_history(customer_id, day_number)`; `customer_preferences.is_active` + partial index; creates `email_templates` (unused by server code). `manual_review` is commented out.

## Tables used by code
| Table | Access | Where |
| --- | --- | --- |
| `customers` | SELECT | customer_repository, recipe_repository (exists check) |
| `customer_preferences` | SELECT (LEFT JOIN, `is_active`) | customer_repository |
| `workflow_runs` | SELECT FOR UPDATE SKIP LOCKED, UPDATE | workflow_repository |
| `recipe_history` | SELECT (cosine `<=>`), INSERT/UPSERT | recipe_repository |

Relations (Inferred from queries): preferences and recipes reference `customers.id`; workflow_runs references customer_id. `insert_recipe` maps `ForeignKeyViolationError` to NotFound; update maps `UniqueViolationError` to Conflict (the `uq_workflow_active` index).

Vectors: 1536 dims, passed as text literal via `app/db.py:to_vector_literal` and cast `$n::vector`; similarity = `1 - (embedding <=> $2)`.

Attempt count capped at 3 in SQL (`LEAST`) and schema.

Sources: qeuries.sql, app/repositories/*.py, app/db.py, README.md
Verified: 2026-11-05
