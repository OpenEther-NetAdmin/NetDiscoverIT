# MSP Portal Group 4 Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add MSP-aware auth middleware, organization-scoped CRUD support, and an overview experience that exposes portal health and tenant activity in a way that is safe for multi-organization use.

**Architecture:** The portal should treat MSP tenancy as a first-class concern at the API boundary, with middleware and dependency guards enforcing org context before any CRUD or overview query runs. The overview layer should aggregate existing device, discovery, and change data through read-only endpoints so the frontend can render a single portal landing page without duplicating business logic.

**Tech Stack:** FastAPI, SQLAlchemy async sessions, JWT auth, React, Chakra UI, existing NetDiscoverIT API schemas, Docker Compose

---

## Overview

Group 4 covers the MSP portal surface that sits on top of the existing NetDiscoverIT data model. The work is intentionally incremental: first establish a reliable auth/multi-org guardrail, then expose tenant-scoped CRUD endpoints, then wire a portal overview that summarizes tenant posture without leaking data across organizations.

The design reuses existing backend models and frontend pages where possible. The main new behavior is org-aware request handling and an overview API that can power the portal landing page, while keeping the current device, discovery, and change screens as the source of truth for detailed workflows.

## Approach Options

### Option 1: Backend-first portal foundation
- Build auth middleware, org-scoped dependencies, and overview aggregation APIs first.
- Reuse existing frontend pages once the API contracts are stable.
- Best when the main risk is data isolation and permission correctness.

### Option 2: Full-stack portal slice
- Implement middleware, CRUD, overview, and portal UI together.
- Provides faster end-to-end feedback but spreads scope across more files.
- Best when a tight demo path matters more than isolated backend correctness.

### Option 3: Docs-only planning pass
- Update the design and implementation docs only.
- No runtime changes, useful when the code is already feature-complete.
- Lowest delivery value if the actual MSP portal still needs implementation.

**Decision:** Option 1. Start with backend auth and organization boundaries, then expose the CRUD/overview APIs that the existing frontend can consume.

## Architecture

### 1. Auth Middleware and Tenant Context
The API should validate the caller's JWT, resolve the user's organization, and expose that context through dependencies instead of ad hoc parsing inside routes. Any MSP-specific request should fail closed if the token is invalid, the user is inactive, or the organization cannot be resolved.

### 2. Organization-Scoped CRUD
CRUD endpoints should continue to use the existing resource patterns, but every query and mutation must be scoped to the caller's organization. The implementation should avoid introducing new tables unless absolutely necessary; the current models already provide enough shape for devices, discoveries, integrations, alerts, and changes.

### 3. Portal Overview
The overview should be a read-only aggregation endpoint that composes counts and recent activity from existing tables. The frontend can render a landing page or dashboard cards from this API, while detailed navigation still points to the current Devices, Discoveries, Path Visualizer, and Settings pages.

## Data Flow

1. User authenticates and receives a JWT.
2. Request enters MSP middleware and resolves the organization context.
3. CRUD handlers query only records within that organization.
4. Overview endpoint aggregates device, discovery, and change metrics for the same org.
5. Frontend consumes the overview response for summary cards and keeps detail workflows on the existing pages.

## Error Handling

- Reject requests with missing or invalid auth before touching the database.
- Return `403` for authenticated users without the required portal role.
- Return `404` for organization-scoped records that do not exist within the caller's tenant.
- Return a safe empty overview payload if tenant data is absent rather than failing the page.
- Keep external failures out of the portal overview path; it should be based on local data only.

## Testing Strategy

### Backend tests
- Verify auth middleware rejects missing, malformed, and inactive-user requests.
- Verify org-scoped CRUD does not leak records across organizations.
- Verify overview aggregation returns correct counts and recent items for one organization.
- Verify admin and non-admin flows where role checks apply.

### Integration tests
- Exercise the authenticated request path through the API container with a seeded organization and user.
- Confirm CRUD calls only return the current tenant's objects.
- Confirm overview responses remain stable when one dataset is empty.

### Frontend tests
- Verify the portal landing page loads summary cards from the overview API.
- Verify navigation still lands on the existing detail pages.
- Verify loading and error states render cleanly when the overview endpoint fails.

## Files in Scope

- Modify: `services/api/app/api/dependencies.py`
- Modify: `services/api/app/api/routes.py`
- Modify: `services/api/app/api/schemas.py`
- Modify: `services/frontend/src/App.js`
- Modify: `services/frontend/src/pages/Dashboard.jsx`
- Modify: `services/frontend/src/pages/Devices.jsx`
- Modify: `services/frontend/src/pages/Discoveries.jsx`
- Modify: `services/frontend/src/pages/PathVisualizer.jsx`
- Modify: `docs/TODO.md`

## Risks and Guardrails

- The largest risk is accidental cross-tenant access; every query path must include organization filters.
- The second risk is overbuilding a new portal abstraction when the existing pages already cover detail workflows.
- The safest implementation is to keep overview logic read-only and centralize access checks in dependencies.
