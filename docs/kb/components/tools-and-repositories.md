# Components: tools and repositories

| Tool function | Repository function | Notes |
| --- | --- | --- |
| `customer_tools.get_customer_profile` | `customer_repository.fetch_customer_profile` | Raises NotFound if customer missing/inactive; builds constraint labels (nut-free, gluten-free, dairy-free, soy-free) |
| `workflow_tools.claim_pending_workflow` | `workflow_repository.claim_pending_workflow` | Transaction; returns None if queue empty |
| `workflow_tools.update_workflow_status` | `workflow_repository.update_workflow_status` | `WHERE id=$1 AND claimed_by=$2`; NotFound if not owner; Conflict on unique violation |
| `recipe_tools.check_duplicate_recipe` | `recipe_repository.find_similar_recipes` | Checks customer exists; `is_duplicate` if any similarity >= threshold |
| `recipe_tools.save_recipe` | `recipe_repository.insert_recipe` | Upsert, returns id |

Tools re-validate arguments via pydantic input models (`app/schemas.py`) and fetch the pool with `app.db.get_pool()`.

Sources: app/tools/*.py, app/repositories/*.py
Verified: 2026-11-05
