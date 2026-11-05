# Design patterns

### Layered tools / repository
Tools validate and delegate; repositories own SQL. `app/tools/customer_tools.py:get_customer_profile` -> `app/repositories/customer_repository.py:fetch_customer_profile`; same for recipe and workflow. Services layer is absent (tools act as thin service).

### Decorator for error masking
`app/server.py:_safe_tool` maps `ToolServiceError` to its message, `ValidationError` to "Invalid tool input", and unexpected errors to a generic message with a reference ID (only type and ref logged).

### Custom exception hierarchy
`app/errors.py:ToolServiceError`, `NotFoundError`, `ConflictError` carry client-safe messages.

### Middleware (auth)
`app/server.py:BearerAuthMiddleware` uses `hmac.compare_digest`, token length cap 4096.

### Singleton / module-level pool
`app/db.py:_pool`, `create_pool`, `get_pool`, `close_pool`. Settings cached by `app/config.py:get_settings` (`lru_cache`).

### Strict DTO models
`app/schemas.py:StrictModel` (`extra="forbid"`, strips whitespace); enums `WorkflowType`, `WorkflowStatus`, `EmailStatus`.

### Work-queue claim with SKIP LOCKED
`app/repositories/workflow_repository.py:claim_pending_workflow` selects `FOR UPDATE SKIP LOCKED` then sets RUNNING in one transaction. Ownership check via `claimed_by` in `UPDATE_WORKFLOW_SQL`.

### Idempotent upsert
`app/repositories/recipe_repository.py:SAVE_RECIPE_SQL` `ON CONFLICT (customer_id, day_number) DO UPDATE`.

### Dependency-injected lifespan
`partial(lifespan, settings=config)` in `create_server`.

Sources: app/server.py, app/errors.py, app/db.py, app/config.py, app/schemas.py, app/repositories/*.py
Verified: 2026-11-05
