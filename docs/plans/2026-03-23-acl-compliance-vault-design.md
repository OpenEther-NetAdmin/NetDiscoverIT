# ACL Compliance Vault + ContainerLab Simulation Design

> **For Claude:** This design combines Group 3 (ACL Compliance Vault) and Group 2d (ContainerLab Simulation) into a coordinated implementation.

**Date:** 2026-03-23

---

## Overview

This document outlines the design for two related features:

1. **ACL Compliance Vault** — Zero-knowledge encrypted storage for firewall rules/ACL content, enabling customers to store compliance evidence without surrendering sensitive data to third parties.

2. **ContainerLab Simulation** — Agent-side topology simulation that validates proposed network changes before they're applied in production.

---

## Architecture

### ACL Compliance Vault

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ Local Agent │────>│  API Server │────>│ PostgreSQL  │
│ (encrypts)  │     │ (stores)    │     │ (ACLSnapshots)│
└─────────────┘     └─────────────┘     └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │ Customer    │ (decrypts with own key)
                    │ (retrieves) │
                    └─────────────┘
```

**Zero-Knowledge Model:**
- Customer holds encryption key (HashiCorp Vault, AWS KMS, Azure Key Vault, GCP CSEK, or self-managed)
- Local agent encrypts ACL content on-prem before sending to API
- We store encrypted blob — cryptographically unreadable to us
- Customer can verify HMAC after decryption to confirm data integrity

### ContainerLab Simulation

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   API       │────>│   Redis     │────>│    Agent    │
│ (triggers)  │     │   Queue     │     │ (executes)  │
└─────────────┘     └─────────────┘     └─────────────┘
       │                                     │
       ▼                                     ▼
┌─────────────┐                       ┌─────────────┐
│ Neo4j       │                       │ ContainerLab│
│ (topology)  │                       │ (simulates) │
└─────────────┘                       └─────────────┘
```

**Workflow:**
1. ChangeRecord in "proposed" status
2. API triggers simulation via Redis queue
3. Agent generates topology YAML from Neo4j
4. Agent runs ContainerLab with proposed config
5. Results stored in ChangeRecord.simulation_results
6. Change cannot be approved unless simulation_passed=true

---

## Components

### 1. ACL Compliance Vault API

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| POST | /acl-snapshots | Upload new ACL snapshot (agent-authenticated) |
| GET | /acl-snapshots | List snapshots with filters |
| GET | /acl-snapshots/{id} | Get specific snapshot |
| DELETE | /acl-snapshots/{id} | Delete snapshot |

**Query Parameters for List:**
- `device_id` - Filter by device
- `content_type` - acl_rules, firewall_policy, nat_rules, security_policy, route_policy
- `compliance_scope` - Filter by scope (PCI-CDE, HIPAA, etc.)
- `captured_after` / `captured_before` - Date range
- `skip`, `limit` - Pagination

**Data Model (already exists):**
```python
class ACLSnapshot:
    id: UUID
    organization_id: UUID
    device_id: UUID
    content_type: str  # acl_rules, firewall_policy, etc.
    encrypted_blob: str  # AES-256-GCM encrypted content
    content_hmac: str  # HMAC-SHA256 for integrity
    plaintext_size_bytes: int
    key_id: str  # Customer's key reference
    key_provider: str  # hashicorp_vault, aws_kms, etc.
    encryption_algorithm: str  # AES-256-GCM
    captured_at: datetime
    captured_by: UUID
    config_hash_at_capture: str
    compliance_scope: list[str]
```

### 2. ContainerLab Simulation Service

**Components:**

1. **Topology Generator Service** (`services/api/app/services/topology_generator.py`)
   - Query Neo4j for device topology
   - Generate ContainerLab YAML topology file
   - Map device configs to ContainerLab nodes

2. **Simulation Queue** - Redis-based job queue
   - Job contains: change_id, proposed_config, device_ids
   - Agent picks up job, executes simulation
   - Results written back to ChangeRecord

3. **API Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| POST | /changes/{id}/simulate | Trigger simulation |
| GET | /changes/{id}/simulation-results | Poll for results |

**Simulation Results Schema:**
```json
{
  "simulation_id": "uuid",
  "status": "pending|running|completed|failed",
  "started_at": "datetime",
  "completed_at": "datetime",
  "topology_file": "s3://...",
  "results": {
    "packet_test": {"passed": true, "details": "..."},
    "connectivity_test": {"passed": true, "details": "..."},
    "acl_analysis": {"passed": true, "details": "..."}
  },
  "passed": true,
  "error": null
}
```

### 3. State Machine Update

Update ChangeRecord state machine to enforce simulation:

```python
VALID_TRANSITIONS = {
    "draft": ["proposed", "deleted"],
    "proposed": ["approved", "draft"],  # Now requires simulation_passed=true
    "approved": ["scheduled", "in_progress", "rolled_back"],
    # ...
}
```

---

## Security Considerations

### ACL Compliance Vault

1. **Key Isolation** — Never store actual encryption keys; only key_id references
2. **Agent Authentication** — Use X-Agent-Key auth for upload endpoint
3. **Organization Isolation** — Verify org_id matches JWT claims
4. **Audit Logging** — Log all snapshot operations

### ContainerLab Simulation

1. **Network Isolation** — ContainerLab runs in isolated network
2. **Config Safety** — Never apply proposed config to production
3. **Timeout Handling** — Max 30 minutes per simulation
4. **Resource Limits** — Limit concurrent simulations per org

---

## Implementation Approach

**Option A: API-Driven (Recommended)**
- API triggers simulation job via Redis
- Agent polls queue, executes ContainerLab
- Results stored in ChangeRecord
- Pros: Centralized control, better audit trail
- Cons: More complex queue management

**Option B: Agent-Orchestrated**
- Agent polls ChangeRecord for pending simulations
- Agent runs ContainerLab directly
- Agent updates ChangeRecord with results
- Pros: Simpler API
- Cons: Less visibility, harder to scale

**Decision:** Option A (API-Driven) — aligns with existing pattern for async tasks (Alert routing, config drift detection)

---

## Dependencies

- **PostgreSQL** — ACLSnapshot table (already exists)
- **Neo4j** — Topology data for ContainerLab YAML generation
- **Redis** — Job queue for simulation tasks
- **Local Agent** — Runs ContainerLab, generates topology YAML

---

## Out of Scope

- Customer key management (customer manages their own keys)
- Compliance report generation (Phase 2 MSP Portal)
- ContainerLab advanced mode (multi-vendor, traffic replay) — Phase 3

---

## Next Steps

1. Create implementation plan with task breakdown
2. Implement ACL Compliance Vault API first (simpler)
3. Implement ContainerLab simulation (more complex)
4. Update state machine to enforce simulation before approval