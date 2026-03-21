# API Authentication & Schema Expansion Design

**Date:** 2026-03-21  
**Status:** Approved

---

## 1. JWT Authentication (Full - Access + Refresh)

### Architecture

- **Access token:** 15 min expiry, Bearer auth header
- **Refresh token:** 7 days expiry, httpOnly cookie + body option
- **Token payload:** `{ sub: user_id, org_id, role, exp, iat }`
- **Refresh endpoint:** Rotates both tokens (refresh token rotation for security)

### Implementation

**Endpoints:**
- `POST /api/v1/auth/login` - email + password → tokens
- `POST /api/v1/auth/refresh` - refresh token → new access + refresh
- `POST /api/v1/auth/logout` - invalidate refresh token

**Files:**
- `app/api/auth.py` - auth routes
- `app/api/dependencies.py` - update get_current_user with JWT decode
- `app/core/security.py` - password hashing (bcrypt), token create/verify

### Dependencies

- `python-jose` - JWT encode/decode
- `passlib[bcrypt]` - password hashing

---

## 2. Agent API Key Auth

### Architecture

- Existing LocalAgent model has `api_key_hash` (bcrypt)
- Agent sends `X-Agent-Key: <plaintext>` header
- Dependency validates against DB hash, returns agent context

### Implementation

**Endpoints:**
- `POST /api/v1/agent/register` - org creates agent, returns API key (plaintext once)
- Update routes: `/agent/vectors`, heartbeat to use agent auth

**Files:**
- `app/api/dependencies.py` - add `get_agent_auth` dependency

---

## 3. Schema Expansion (Users, Credentials, Integrations)

### User Schemas

| Schema | Description |
|--------|-------------|
| `UserLogin` | email + password |
| `UserCreate` | email, password, full_name, role, organization_id |
| `UserUpdate` | optional: email, full_name, role, password |
| `UserResponse` | excludes hashed_password |
| `TokenResponse` | access_token, refresh_token, token_type |

### Credential Schemas

| Schema | Description |
|--------|-------------|
| `CredentialCreate` | name, username, password, credential_type, target_filter |
| `CredentialResponse` | excludes encrypted_password |
| `CredentialType` | Enum: password, ssh_key, api_token, snmp_community |

### Integration Schemas

| Schema | Description |
|--------|-------------|
| `IntegrationConfigCreate` | integration_type, name, base_url, config |
| `IntegrationConfigResponse` | excludes encrypted_credentials, webhook_secret |

---

## Implementation Priority

1. **Phase 1:** Core security module + JWT auth endpoints
2. **Phase 2:** Update routes with proper auth dependencies
3. **Phase 3:** Expand user schemas
4. **Phase 4:** Credential & integration schemas

---

## Notes

- Alerts & monitoring schemas deferred until after initial launch
- Agent heartbeat endpoint not specified yet - will add as discovered
- MSP multi-org access handled via existing UserOrgAccess model
