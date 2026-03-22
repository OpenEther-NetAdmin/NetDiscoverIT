# Group 2 — Change Management API Design

> **Created:** 2026-03-22  
> **Based on:** claw-memory/phase2-work-plan.md Group 2  
> **Status:** Design - awaiting implementation

---

## Overview

Design document for implementing the Change Management API - the primary evidence artifact for compliance audits (PCI-DSS Req 6, SOX ITGC change management, ISO 27001 A.12.1.2). This API provides full CRUD operations and state machine transitions for ChangeRecord entities.

---

## Architecture

### High-Level Design

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         NetDiscoverIT API                               │
├─────────────────────────────────────────────────────────────────────────┤
│  Change Management API Layer                                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │  2a CRUD    │  │  2b State   │  │  2c Ticket  │  │  2d ContainerLab│
│  │  Endpoints  │→ │  Transitions│→ │  Sync       │→ │  Simulation │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘ │
│         ↓               ↓               ↓               ↓              │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │                    PostgreSQL (ChangeRecord)                     │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│         ↓               ↓               ↓                             │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │              External Integrations (async)                      │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐    │  │
│  │  │ServiceNow│  │   JIRA   │  │ContainerLab│ │  Webhook     │    │  │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────────┘    │  │
│  └─────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

### Components

| Component | Purpose |
|-----------|---------|
| `ChangeRecord` model | Already exists in `models/models.py` with full lifecycle fields |
| CRUD endpoints | Create, read, update, delete ChangeRecord entities |
| State machine | Enforce lifecycle: `draft → proposed → approved → implemented → verified` |
| Ticket sync | Auto-create/update tickets in ServiceNow/JIRA |
| ContainerLab | On-prem simulation for proposed changes |
| Webhook receiver | Handle external approval callbacks |

---

## Data Model

### ChangeRecord (existing in models/models.py)

The `ChangeRecord` model already exists with the following key fields:

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `organization_id` | UUID | FK to Organization |
| `change_number` | String(50) | Human-readable (CHG-2026-0042) |
| `status` | String(50) | Lifecycle state |
| `change_type` | String(50) | config_change, firmware_upgrade, acl_update, etc. |
| `title` | String(500) | Change title |
| `description` | Text | Detailed description |
| `risk_level` | String(20) | low, medium, high, critical |
| `affected_devices` | JSONB | List of device IDs |
| `affected_compliance_scopes` | JSONB | e.g. ["PCI-CDE", "SOX-FINANCIAL"] |
| `requested_by` | UUID | FK to User |
| `approved_by` | UUID | FK to User |
| `proposed_change_hash` | String(64) | SHA-256 of proposed config |
| `pre_change_hash` | String(64) | config_hash before change |
| `post_change_hash` | String(64) | config_hash after change |
| `simulation_performed` | Boolean | Whether simulation run |
| `simulation_results` | JSONB | Simulation test results |
| `simulation_passed` | Boolean | Simulation pass/fail |
| `external_ticket_id` | String(255) | ServiceNow sys_id, JIRA key |
| `external_ticket_url` | String(2048) | Direct link |
| `ticket_system` | String(50) | servicenow, jira, etc. |

### Lifecycle States

```
draft → pending_approval → approved → scheduled → in_progress → completed
                                           ↓                        ↓
                                      rolled_back ←────────── failed
```

---

## API Endpoints Design

### 2a. ChangeRecord CRUD

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/changes` | Create new change record (status=draft, generate CHG-YYYY-NNNN) |
| GET | `/api/v1/changes` | List with filters (status, risk_level, device, compliance_scope) |
| GET | `/api/v1/changes/{id}` | Get change detail |
| PATCH | `/api/v1/changes/{id}` | Update fields (draft/proposed only) |
| DELETE | `/api/v1/changes/{id}` | Soft-delete (draft only) |

### 2b. State Transitions

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/changes/{id}/propose` | Submit for review; capture pre_change_hash |
| POST | `/api/v1/changes/{id}/approve` | Record approved_by + approved_at + notes; require admin role |
| POST | `/api/v1/changes/{id}/implement` | Record implementation_evidence; capture post_change_hash |
| POST | `/api/v1/changes/{id}/verify` | Record verification_results; close change |
| POST | `/api/v1/changes/{id}/rollback` | Transition to rolled_back; capture rollback_evidence |

### 2c. External Ticket Sync

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/changes/{id}/sync-ticket` | Manually sync to external ticketing system |
| POST | `/api/v1/webhooks/change/{integration_id}` | Webhook receiver for external approval |

### 2d. ContainerLab Simulation

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/changes/{id}/simulate` | Trigger ContainerLab simulation |
| GET | `/api/v1/changes/{id}/simulation-results` | Get simulation results |

---

## Security & Validation

### Role-Based Access

- **admin**: Can approve changes, view all org changes
- **engineer**: Can create, propose, implement changes
- **viewer**: Read-only access

### State Transition Rules

| Transition | Required Role | Preconditions |
|------------|---------------|---------------|
| draft → proposed | engineer | affected_devices populated |
| proposed → approved | admin | simulation_passed=true (if simulation_performed) |
| approved → implemented | engineer | scheduled_window respected |
| implemented → verified | admin | implementation_evidence verified |
| any → rolled_back | admin | rollback_plan exists |

### Audit Trail

All state transitions write to AuditLog:
- `action`: `change_record.transition`
- `resource_id`: ChangeRecord UUID
- `details`: `{ from_status, to_status, triggered_by, timestamp }`

---

## External Integration Design

### ServiceNow Integration

```
ChangeRecord proposed → Create Change Request in ServiceNow
                          ↓
                    Store external_ticket_id, external_ticket_url
                          ↓
              Webhook receives CAB approval → Auto-approve in NetDiscoverIT
```

API: `POST /api/now/table/change_request`

### JIRA Integration

```
ChangeRecord proposed → Create Issue in JIRA
                          ↓
                    Store external_ticket_id, external_ticket_url
                          ↓
              Webhook receives approval → Auto-approve in NetDiscoverIT
```

API: `POST /rest/api/3/issue`

### ContainerLab Simulation

```
1. API receives /simulate request
2. Agent generates topology YAML from Neo4j graph
3. Agent spins ContainerLab topology
4. Agent applies proposed change config
5. Agent captures results (pass/fail, traffic impact, convergence)
6. Results uploaded to API → simulation_results + simulation_passed
```

---

## Error Handling

| Error | HTTP Code | Description |
|-------|-----------|-------------|
| Invalid state transition | 400 | Transition not allowed from current state |
| Simulation required | 400 | Simulation must pass before approval |
| Unauthorized | 403 | User lacks required role |
| Not found | 404 | ChangeRecord doesn't exist |
| External API failure | 502 | ServiceNow/JIRA unreachable |

---

## Testing Strategy

### Unit Tests

- State transition validation logic
- Change number generation (CHG-YYYY-NNNN)
- Role permission checks
- Schema serialization/deserialization

### Integration Tests

- CRUD endpoint flow
- Full lifecycle transitions
- ServiceNow/JIRA mock integration
- Webhook receiver

### E2E Tests

- Complete change workflow: draft → propose → approve → implement → verify
- ContainerLab simulation trigger (mocked)

---

## Dependencies

- **Group 1b**: IntegrationConfig CRUD (for ticket sync)
- **models/models.py**: ChangeRecord model already exists
- **api/dependencies.py**: Role checking utilities
- **api/schemas.py**: ChangeRecord schemas to be created

---

## Estimated Effort

| Task | Effort |
|------|--------|
| 2a. ChangeRecord CRUD | ~3 hours |
| 2b. State Transitions | ~4 hours |
| 2c. External Ticket Sync | ~6 hours |
| 2d. ContainerLab Simulation | ~8 hours |

**Total: ~21 hours**

---

## Acceptance Criteria

1. All CRUD endpoints functional and return correct response schemas
2. State machine enforces valid transitions only
3. Role-based access control enforced on all endpoints
4. AuditLog entries created for all state transitions
5. ServiceNow/JIRA integration creates and syncs tickets
6. ContainerLab simulation can be triggered and results stored
7. All endpoints have unit and integration tests
8. API documentation updated with OpenAPI specs
