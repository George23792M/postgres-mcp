# Implementation Summary: get_welcome_email Tool

## Overview
Implemented a new `get_active_email_template` tool in the postgres-mcp project to fetch active email templates from the database by name.

## Files Created

### 1. app/repositories/email_repository.py
- New repository module for email template database operations
- Function: `active_email_template(pool, template_name)` 
  - Queries the `email_templates` table for active templates by name
  - Returns None if not found, or a dict with template data
  - Transforms `body_html` from database to match the expected response contract
  - Returns: `{"active": True, "subject": "...", "html_body": "..."}`

### 2. app/tools/email_tools.py
- New tool module exposing MCP tool interface
- Function: `get_active_email_template(template_name)`
  - Accepts template_name as validated string (1-100 chars)
  - Uses `_database_result()` for error handling
  - Returns `{"found": False}` when template not found
  - Returns `{"found": True, "template": {...}}` on success
  - Follows the same error handling pattern as subscription_tools.py

### 3. tests/test_email_tools.py
- Basic test file for the new tool (can be expanded)

## Files Modified

### app/server.py
- Added import: `from app.tools.email_tools import get_active_email_template`
- Registered tool in `_register_tools()` function with description

## Database Requirements
The implementation expects the `email_templates` table with these columns:
- template_name (VARCHAR)
- subject (TEXT)
- body_html (TEXT)
- status (VARCHAR) - must be 'ACTIVE' for the active index

## Contract
Tool response format:
- **Not Found**: `{"found": False}`
- **Found**: `{"found": True, "template": {"active": True, "subject": "...", "html_body": "..."}}`

This matches the expected contract for the smoothie-email-subscription-service's `active_welcome_template()` method.

## Integration
The smoothie-email-subscription-service calls this tool via:
```python
payload = await self.client.call("get_active_email_template", {"template_name": "welcome"})
```

## Standards Compliance
✓ Functions under 30 lines
✓ Follows existing repository/tool pattern
✓ Uses Annotated for parameter validation
✓ Error handling via `_database_result()` and existing error mapping
✓ Proper docstrings and type hints
✓ OWASP: No SQL injection (parameterized queries), no secrets in code
