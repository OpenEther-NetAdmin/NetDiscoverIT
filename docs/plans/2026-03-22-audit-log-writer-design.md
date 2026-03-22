# AuditLog Writer Design

**Date:** 2026-03-22
**Status:** Approved

## Overview

Implement a FastAPI dependency that automatically logs every authenticated request to sensitive resources to the AuditLog table (PCI-DSS Req 10).

## Architecture

```
Request → Auth Middleware → Route Handler → AuditLog Dependency → Database
                                              ↓
                                    Extract: user_id, action, 
                                    resource_type, resource_id,
                                    ip_address, user_agent
```

## Implementation

### 1. AuditLog Dependency

Location: `services/api/app/api/dependencies.py`

```python
async def audit_log(
    action: str,
    resource_type: str,
    resource_id: str = None,
    resource_name: str = None,
    outcome: str = "success",
    details: dict = {},
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Write audit log entry"""
    # Extract client info from request context
    # Write to AuditLog table
```

### 2. Audit Decorator

```python
def audit_action(action: str, resource_type: str):
    """Decorator to auto-log route actions"""
    # Extracts route params, applies audit_log
```

### 3. Apply to Existing Routes

- Device CRUD endpoints
- Site CRUD endpoints  
- Agent management endpoints
- Credential endpoints (sensitive)
- Discovery endpoints

## Data Captured

| Field | Source |
|-------|--------|
| `user_id` | JWT payload (`sub`) |
| `organization_id` | JWT payload (`org_id`) |
| `action` | Passed via decorator (e.g., `device.view`, `device.create`) |
| `resource_type` | Passed via decorator |
| `resource_id` | Route path parameter |
| `resource_name` | Extracted from request body (e.g., hostname) |
| `outcome` | success/failure |
| `ip_address` | `request.client.host` |
| `user_agent` | Request headers |

## Action Format

- `device.view` — user viewed device detail
- `device.create` — user created device
- `device.update` — user updated device
- `device.delete` — user deleted device
- `site.view` — user viewed site
- `site.create` — user created site
- `agent.view` — user viewed agent
- `credential.access` — user accessed credential
- `user.login` — successful authentication
- `user.login_failed` — failed authentication

## Testing

- Unit tests for audit_log function
- Integration tests verifying log entries are created
- Verify sensitive operations are logged correctly
