# Group 6a Design: Vectorizer Pipeline (sentence-transformers all-mpnet-base-v2)

> **Based on:** claw-memory/phase2-work-plan.md Group 6a  
> **Created:** 2026-03-23  
> **Status:** Design approved

---

## Overview

Upgrade the local agent's vectorizer to use `sentence-transformers/all-mpnet-base-v2` model (768 dimensions) instead of the current `all-MiniLM-L6-v2` (384 dimensions). Add a 4th vector type (`config_vector`) for configuration similarity search. All vector generation happens on-prem, maintaining the privacy-first architecture.

---

## Background

### Current State
- **Model:** `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions)
- **Vector types:** 3 (role_vector, topology_vector, security_vector)
- **Storage:** PostgreSQL with pgvector (4 × 768-dim columns already exist)

### Requirement
- **Model:** `sentence-transformers/all-mpnet-base-v2` (768 dimensions)
- **Vector types:** 4 (add config_vector from normalized config text)
- **Privacy:** All generation on-prem; only float arrays leave the customer network

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Local Agent (On-Prem)                           │
├─────────────────────────────────────────────────────────────────────┤
│  collector → normalizer → sanitizer → vectorizer → uploader       │
│                                           │                         │
│                              ┌────────────┴────────────┐           │
│                              │   SentenceTransformer   │           │
│                              │   all-mpnet-base-v2    │           │
│                              │   (768-dim embeddings) │           │
│                              └─────────────────────────┘           │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────────┐
                    │   Upload to Cloud   │
                    │  (4 × 768-dim arrays)│
                    └─────────────────────┘
```

---

## Data Flow

### Vector Generation (per device)

| Vector Column | Embed From | Description |
|---------------|------------|-------------|
| `config_vector` | TextFSM-normalized config (serialized JSON) | Full config semantic fingerprint |
| `role_vector` | Metadata: protocols enabled, port patterns, interface roles | Device functional role |
| `security_vector` | Security posture fields: SSH/telnet/HTTP/SNMP state, ACL presence, AAA | Security configuration |
| `topology_vector` | Connectivity context: neighbor count, BGP/OSPF topology position | Network position |

### Upload Integration
- `POST /api/v1/agents/{agent_id}/upload` accepts device metadata + vectors
- Vectors stored in `Device` table (role_vector, topology_vector, security_vector, config_vector)
- pgvector HNSW indexes already exist (migration 002)

---

## Implementation Scope

### 1. Agent: vectorizer.py
- Change model from `all-MiniLM-L6-v2` to `all-mpnet-base-v2`
- Add `_generate_config_vector()` method using normalized config
- Update `_build_config_description()` to serialize TextFSM output
- Ensure deterministic serialization (sorted keys, consistent formatting)

### 2. API: schemas.py
- Add vector fields to `DeviceMetadataUpload` schema (role_vector, topology_vector, security_vector, config_vector)

### 3. API: routes.py
- Update `upload_agent_data()` to accept and store vectors
- Map incoming vector fields to Device model columns

---

## Privacy Considerations

- Vector embeddings are mathematically one-way — original text cannot be reconstructed
- Only the 768-dim float arrays leave the customer network
- No raw configs or sanitized configs are uploaded
- This aligns with the existing privacy invariant: "raw device configs NEVER leave customer network"

---

## Trade-offs

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| Model choice | all-mpnet-base-v2 | Best-in-class for semantic similarity; 768 dims matches existing schema |
| Config embedding | Full normalized text | Preserves signal for drift detection, similarity search, anomaly detection |
| Caching | Not included | Can be added as optimization if profiling shows bottleneck |

---

## Dependencies

- **Group 5 (TextFSM Normalization):** Must complete first — config_vector requires normalized config output
- **sentence-transformers package:** Already installed (==3.3.1 in agent requirements.txt)

---

## Testing Strategy

1. **Unit tests:** Verify vector dimensions (768), deterministic output, fallback behavior
2. **Integration test:** Full pipeline collector→normalizer→vectorizer→uploader
3. **API test:** Upload endpoint accepts and stores all 4 vectors

---

## Estimated Effort

~4 hours (as per phase2-work-plan.md)