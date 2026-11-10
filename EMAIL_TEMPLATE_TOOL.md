# Email Template Tool Documentation

## New Tool: `get_active_email_template`

### Purpose
Fetches the active email template for a given template name from the PostgreSQL database. This tool is used by the smoothie-email-subscription-service to retrieve email templates before sending emails to users.

### Function Signature
```python
async def get_active_email_template(
    template_name: Annotated[str, Field(min_length=1, max_length=100)],
) -> dict[str, Any]
```

### Parameters
- **template_name** (str, 1-100 characters): The name of the email template to retrieve (e.g., "welcome")

### Response Format

#### Template Found
```json
{
    "found": true,
    "template": {
        "active": true,
        "subject": "Welcome to Our Service!",
        "html_body": "<html>...</html>"
    }
}
```

#### Template Not Found
```json
{
    "found": false
}
```

### Database Requirements
The tool expects the `email_templates` table with the following structure:
- `id` (UUID): Primary key
- `template_name` (VARCHAR): Name of the template
- `subject` (TEXT): Email subject line
- `body_html` (TEXT): HTML content of the email
- `status` (VARCHAR): Status of the template ("ACTIVE", etc.)

### Error Handling
The tool handles database errors gracefully using the existing `_database_result()` pattern:
- Connection timeouts and OSError → `DatabaseUnavailableError`
- PostgreSQL errors → Mapped through `map_database_error()` for safe client responses

### Usage Example
```python
# Called by smoothie-email-subscription-service
payload = await client.call("get_active_email_template", {"template_name": "welcome"})

if payload["found"]:
    subject = payload["template"]["subject"]
    html_body = payload["template"]["html_body"]
    # Send email...
```

### Implementation Details
- **File**: `app/tools/email_tools.py`
- **Repository**: `app/repositories/email_repository.py`
- **Registered in**: `app/server.py`
- **Tests**: `tests/test_email_tools.py`

### Security
- Uses parameterized queries to prevent SQL injection
- Validates template_name length (1-100 characters)
- Only returns templates with "ACTIVE" status
- No secrets or sensitive data exposed in errors
