# MSP Portal Group 4 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement MSP portal auth middleware, tenant-scoped CRUD support, and a portal overview that summarizes per-organization activity for the existing frontend.

**Architecture:** The implementation should concentrate permission checks in API dependencies, keep CRUD handlers organization-aware, and expose one read-only overview endpoint that powers the portal landing page. The frontend should reuse the existing pages for detailed workflows while the dashboard becomes the MSP summary entrypoint.

**Tech Stack:** FastAPI, SQLAlchemy async, JWT auth, React, Chakra UI, pytest, Docker Compose

---

### Task 1: MSP auth middleware and tenant context

**Files:**
- Modify: `services/api/app/api/dependencies.py`
- Modify: `services/api/app/api/schemas.py`
- Test: `services/api/tests/api/test_auth.py`
- Test: `services/api/tests/api/test_audit_log.py`

**Step 1: Write the failing test**

Add a test that calls the protected API with an invalid or inactive user and expects `401` or `403`, plus a test that verifies the resolved auth context includes organization data for a valid token.

**Step 2: Run test to verify it fails**

Run: `docker exec -w /app netdiscoverit-api python -m pytest tests/api/test_auth.py -v`
Expected: fail until the middleware dependency and schema are aligned.

**Step 3: Write minimal implementation**

Update the auth dependency so it returns a typed organization-aware context object and keep the inactive-user guard closed.

**Step 4: Run test to verify it passes**

Run: `docker exec -w /app netdiscoverit-api python -m pytest tests/api/test_auth.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add services/api/app/api/dependencies.py services/api/app/api/schemas.py services/api/tests/api/test_auth.py services/api/tests/api/test_audit_log.py
git commit -m "feat: add MSP auth context guards"
```

### Task 2: Organization-scoped CRUD hardening

**Files:**
- Modify: `services/api/app/api/routes.py`
- Test: `services/api/tests/api/test_device_audit.py`
- Test: `services/api/tests/api/test_audit_integration.py`

**Step 1: Write the failing test**

Add tests that seed two organizations and verify CRUD handlers only return records for the authenticated user’s organization.

**Step 2: Run test to verify it fails**

Run: `docker exec -w /app netdiscoverit-api python -m pytest tests/api/test_device_audit.py tests/api/test_audit_integration.py -v`
Expected: failure until every query uses the org filter.

**Step 3: Write minimal implementation**

Replace any ad hoc access checks with consistent org-scoped filters in CRUD and read handlers.

**Step 4: Run test to verify it passes**

Run: `docker exec -w /app netdiscoverit-api python -m pytest tests/api/test_device_audit.py tests/api/test_audit_integration.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add services/api/app/api/routes.py services/api/tests/api/test_device_audit.py services/api/tests/api/test_audit_integration.py
git commit -m "feat: scope CRUD operations to tenant context"
```

### Task 3: Portal overview endpoint and frontend landing page

**Files:**
- Modify: `services/api/app/api/routes.py`
- Modify: `services/api/app/api/schemas.py`
- Modify: `services/frontend/src/pages/Dashboard.jsx`
- Modify: `services/frontend/src/App.js`
- Test: `services/frontend/src/pages/Dashboard.jsx`

**Step 1: Write the failing test**

Add a backend test for the overview endpoint and a frontend test or snapshot that asserts the dashboard renders summary data from the overview response.

**Step 2: Run test to verify it fails**

Run: `docker exec -w /app netdiscoverit-api python -m pytest tests/api -v`
Expected: overview test fails until the endpoint exists.

**Step 3: Write minimal implementation**

Add a read-only overview schema and endpoint, then wire `Dashboard.jsx` to consume it as the portal landing page.

**Step 4: Run test to verify it passes**

Run: `docker exec -w /app netdiscoverit-api python -m pytest tests/api -v`
Run: `docker exec -w /app netdiscoverit-frontend npm test -- --watch=false`
Expected: PASS.

**Step 5: Commit**

```bash
git add services/api/app/api/routes.py services/api/app/api/schemas.py services/frontend/src/pages/Dashboard.jsx services/frontend/src/App.js
git commit -m "feat: add MSP portal overview"
```

### Task 4: Documentation and work tracking

**Files:**
- Modify: `docs/TODO.md`
- Modify: `docs/plans/2026-03-23-msp-portal-group4-design.md`
- Modify: `docs/plans/2026-03-23-msp-portal-group4-implementation.md`

**Step 1: Write the docs update**

Mark the MSP portal Group 4 items in the TODO file and keep the design/implementation docs aligned with the approved scope.

**Step 2: Validate the docs**

Run: `docker exec -w /app netdiscoverit-api python -m pytest tests/ -v`
Expected: existing tests continue to pass; docs updates should not affect runtime.

**Step 3: Commit**

```bash
git add docs/TODO.md docs/plans/2026-03-23-msp-portal-group4-design.md docs/plans/2026-03-23-msp-portal-group4-implementation.md
git commit -m "docs: add MSP portal group 4 plan"
```
