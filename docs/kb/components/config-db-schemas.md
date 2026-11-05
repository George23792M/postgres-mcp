# Components: config, db, schemas, errors

- `app/config.py:Settings` (pydantic-settings; `.env`, `extra="ignore"`, secrets as `SecretStr`, `hide_input_in_errors`). `get_settings` is cached.
- `app/db.py`: `create_pool` (idempotent, uses pool size and command timeout settings), `close_pool`, `get_pool` (RuntimeError before startup), `to_vector_literal` (rejects empty, bool, non-finite).
- `app/schemas.py`: input/output models; embeddings exactly 1536 finite floats; `WorkflowStatusUpdate.validation_errors` must be single-line and not contain "traceback" (case-insensitive); `DietaryConstraints.days` 1-30.
- `app/errors.py`: `ToolServiceError`, `NotFoundError`, `ConflictError`.

Sources: app/config.py, app/db.py, app/schemas.py, app/errors.py
Verified: 2026-11-05
