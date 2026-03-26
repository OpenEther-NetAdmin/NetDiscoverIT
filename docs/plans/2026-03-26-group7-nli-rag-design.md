# Group 7 — NLI / RAG Design

**Date:** 2026-03-26
**Status:** Approved
**Depends on:** Group 6a (Vectorizer — all-mpnet-base-v2, Device vector columns populated)

---

## Overview

Group 7 adds a Natural Language Interface (NLI) to NetDiscoverIT. Engineers and auditors can ask plain-English questions about their network and receive answers grounded in real device data — no SQL, no Cypher, no dashboard hunting.

**Scope:** A single `POST /api/v1/query` endpoint backed by a five-stage RAG pipeline that combines pgvector similarity search, Neo4j graph traversal, and Claude API synthesis.

**Out of scope:** streaming responses, conversation history / session context, frontend UI (Group 9), compliance report generation (Group 8b).

---

## Query Types Supported

| Domain | Example questions |
|--------|------------------|
| Topology | "What connects to core-router-01?" / "What is the path from host A to firewall B?" |
| Security | "Which devices have Telnet enabled?" / "Which devices have no SSH configured?" |
| Compliance | "Which devices are in PCI scope?" / "Show me HIPAA-tagged devices" |
| Change management | "What changed on the firewall last week?" / "Are there any unapproved changes?" |
| Inventory | "How many Cisco devices do we have?" / "List all edge routers" |

---

## Architecture: Five-Stage Pipeline

```
POST /api/v1/query  { "question": "..." }
          │
          ▼
┌─────────────────────┐
│  1. IntentClassifier│  embed question → cosine sim vs domain centroids
│                     │  keyword scan → set needs_graph flag
└─────────┬───────────┘
          │  QueryIntent(domains, needs_graph, extracted_entities)
          ▼
┌─────────────────────┐
│  2. VectorRetriever │  pgvector cosine search on selected column(s)
│                     │  enrich: pull ChangeRecords / AlertEvents per device
└─────────┬───────────┘
          │  List[DeviceContext]
          ▼
┌─────────────────────┐
│  3. GraphTraverser  │  (only when needs_graph=True)
│     (Neo4j)         │  neighborhood / shortestPath / VLAN segmentation
└─────────┬───────────┘
          │  GraphContext(nodes, edges, path)
          ▼
┌─────────────────────┐
│  4. ContextBuilder  │  serialise retrieved data → token-budgeted text block
│                     │  max 8,000 context tokens; truncates metadata first
└─────────┬───────────┘
          │  str (prompt context)
          ▼
┌─────────────────────┐
│  5. ClaudeSynthesizer│ single AsyncAnthropic.messages.create() call
│     (claude-sonnet) │  returns answer + structured JSON confidence block
└─────────┬───────────┘
          │
          ▼
POST response: NLIResponse
```

---

## Stage 1 — IntentClassifier

### Embedding signal
The question is embedded with `sentence-transformers/all-mpnet-base-v2` (same model as Group 6a vectorizer). The result is compared via cosine similarity against **domain centroid vectors** — the mean of each Device vector column across the requesting org's devices, computed once per org and cached in an in-process LRU cache (TTL 5 minutes, invalidated on device upload).

Domain → vector column mapping:

| Domain | Column |
|--------|--------|
| inventory / role | `role_vector` |
| topology | `topology_vector` |
| security | `security_vector` |
| config / changes | `config_vector` |

Domains whose centroid similarity exceeds 0.35 are selected. If none clear the threshold, all four domains are searched (fallback broadens recall).

### Keyword signal
Compiled regex patterns detect topology language (`connect`, `path`, `neighbor`, `upstream`, `hop`, `reach`, `route to`, `next.hop`). Any match sets `needs_graph=True`.

### Output
```python
@dataclass
class QueryIntent:
    domains: List[str]          # e.g. ["topology", "security"]
    needs_graph: bool
    extracted_entities: List[str]  # hostnames/IPs extracted by regex
```

---

## Stage 2 — VectorRetriever

Executes one async pgvector query per selected domain:

```sql
SELECT id, hostname, vendor, device_type, metadata, compliance_scope,
       1 - (<vector_column> <=> :query_vec) AS similarity
FROM devices
WHERE organization_id = :org_id
ORDER BY <vector_column> <=> :query_vec
LIMIT :k
```

Default `k = 5` per domain; configurable via `NLI_VECTOR_TOP_K` env var.

**Enrichment (fetched in the same async gather):**
- Security domain: recent `AlertEvent` rows (last 30 days) for matched devices
- Changes domain: `ChangeRecord` rows (last 90 days) for matched devices
- Compliance domain: device `compliance_scope` JSONB (already on the Device row)

Returns `List[DeviceContext]` — each item holds device fields plus enrichment data.

---

## Stage 3 — GraphTraverser

Only invoked when `QueryIntent.needs_graph = True`. Wraps `Neo4jClient` (existing `db/neo4j.py`).

Three query shapes selected by keywords in the question:

| Signal | Neo4j query |
|--------|-------------|
| "connects to X", "neighbors of X" | 2-hop neighborhood from device node |
| "path from X to Y" | `shortestPath` (existing `find_path` method) |
| "segment", "VLAN", "same network as X" | `MEMBER_OF` VLAN traversal |

Device IDs for anchor nodes come from `QueryIntent.extracted_entities` cross-referenced against `VectorRetriever` results (highest-similarity device is used as the anchor if no hostname appears in the question).

Returns `GraphContext`:
```python
@dataclass
class GraphContext:
    nodes: List[dict]        # device properties
    edges: List[dict]        # relationship type + endpoint IDs
    path: Optional[List[str]]  # ordered hostname list for path queries
    query_shape: str         # "neighborhood" | "path" | "vlan"
```

Capped at 50 nodes. If Neo4j is unreachable, `GraphTraverser` logs a warning and returns `None` — the pipeline continues with vector-only context.

---

## Stage 4 — ContextBuilder

Serialises `List[DeviceContext]` + `Optional[GraphContext]` into a prompt-ready text block.

**Token budget:** 8,000 tokens max (leaves ~4k for Claude's answer within a 12k window). Measured with `tiktoken` cl100k_base approximation.

**Truncation order (drop lowest-priority first):**
1. Change record details (keep summary only)
2. Graph edges (keep node list, drop edge list)
3. Device metadata fields (keep hostname, role, security_posture; drop routing counts)

**Output format** (human-readable, not JSON — Claude reads prose better than raw JSON for synthesis):

```
=== NETWORK CONTEXT ===
Device: core-router-01 (192.168.1.1)
  Vendor: Cisco | Type: router | Role: core_router
  Security: SSH=enabled, Telnet=disabled, SNMP=enabled, HTTP=disabled
  Interfaces: 24 | BGP neighbors: 4 | OSPF areas: 1
  Compliance scope: PCI-BOUNDARY, SOC2
  [Source: role similarity=0.91]

Device: edge-fw-01 (10.0.0.1)
  ...

=== TOPOLOGY ===
core-router-01 -- CONNECTED_TO --> edge-fw-01 (via GigabitEthernet0/0)
edge-fw-01 -- CONNECTED_TO --> dmz-switch-01

=== RECENT CHANGES (last 90 days) ===
CHG-2026-0042 | core-router-01 | implemented | 2026-03-20 | BGP policy update
```

Also returns a `sources` list (device IDs + hostnames + similarities) for the API response.

---

## Stage 5 — ClaudeSynthesizer

Single `AsyncAnthropic().messages.create()` call.

**Model:** `claude-sonnet-4-6` (matches `settings.ANTHROPIC_MODEL`)
**Max tokens:** 1,024 (answers should be concise)
**Timeout:** 10 seconds

**System prompt** (abbreviated):
```
You are a network documentation assistant for NetDiscoverIT. Answer questions using
ONLY the provided network context. Cite device hostnames. If context is insufficient,
say so explicitly — never invent device names or facts.

Always end your response with a JSON block on the last line:
{"confidence": <0.0-1.0>, "query_type": "<topology|security|compliance|changes|inventory>", "source_device_ids": ["<uuid>", ...]}
```

**Confidence extraction:** The last line of Claude's response is parsed as JSON. If parsing fails, `confidence = 0.5` and `source_device_ids = []` (all matched devices are returned as sources).

**API key guard:** `NLIService.__init__` checks `settings.ANTHROPIC_API_KEY` at construction time and sets `self.available = False` if empty (logs a warning). The `nli.py` route handler checks `nli_service.available` and returns `503` before doing any work. The app still starts normally — NLI is an optional capability.

---

## New Files

```
services/api/app/
  api/
    routes/nli.py                     ← POST /query route
  services/
    nli/
      __init__.py                     ← exports NLIService
      intent_classifier.py            ← embedding + keyword routing
      vector_retriever.py             ← pgvector search per domain
      graph_traverser.py              ← Neo4j queries for NLI
      context_builder.py              ← serialise to prompt text
      claude_synthesizer.py           ← Anthropic API wrapper
      nli_service.py                  ← orchestrator
```

**Modified files:**
- `services/api/app/api/schemas.py` — add `NLIQuery`, `NLIResponse`, `NLISource`
- `services/api/app/api/routes/__init__.py` — include `nli.router`
- `services/api/requirements.txt` — add `sentence-transformers`, `anthropic`, `tiktoken`

---

## API Contract

### Request
```
POST /api/v1/query
Authorization: Bearer <jwt>
Content-Type: application/json

{
  "question": "Which devices have Telnet enabled?",
  "top_k": 5          // optional, default 5, max 20
}
```

### Response 200
```json
{
  "answer": "Three devices have Telnet enabled: access-sw-01 (10.1.1.1), access-sw-02 (10.1.1.2), and legacy-router-01 (10.2.0.1). These are in the branch site. Telnet is a cleartext protocol — consider disabling it and enabling SSH on these devices.",
  "sources": [
    {"device_id": "uuid-1", "hostname": "access-sw-01", "similarity": 0.94},
    {"device_id": "uuid-2", "hostname": "access-sw-02", "similarity": 0.91},
    {"device_id": "uuid-3", "hostname": "legacy-router-01", "similarity": 0.87}
  ],
  "confidence": 0.92,
  "query_type": "security",
  "retrieved_device_count": 3,
  "graph_traversal_used": false
}
```

### Error responses
| Code | Condition |
|------|-----------|
| 400 | Empty question string |
| 401 | No/invalid JWT |
| 429 | Rate limit exceeded (10/minute per org) |
| 503 | ANTHROPIC_API_KEY not configured |
| 504 | Claude API timeout |

---

## Rate Limiting

`10/minute` per org on `/query`. Enforced via existing `slowapi` limiter with `get_remote_address` as the key function, same as other write endpoints.

---

## Dependencies Added

```
# services/api/requirements.txt additions
sentence-transformers>=2.7.0
anthropic>=0.40.0
tiktoken>=0.7.0
```

`sentence-transformers` is CPU-only in the API container (no GPU, model loaded once at startup via `NLIService.__init__`). Cold start adds ~3s to first request; subsequent requests use cached model.

---

## Testing Strategy

### Unit tests (`tests/api/test_nli_*.py`)
- `IntentClassifier`: topology keywords trigger `needs_graph=True`; ambiguous questions default to all domains; similarity threshold respected
- `ContextBuilder`: truncation respects 8k token budget; source list populated correctly; empty device list handled gracefully
- `VectorRetriever`: SQL query uses correct column per domain; `top_k` clamped to 20
- `GraphTraverser`: correct query shape selected per keyword; Neo4j failure returns `None` (no exception)
- `ClaudeSynthesizer`: confidence JSON parsed correctly; malformed JSON falls back to 0.5; timeout raises correct error

### Integration tests (`tests/api/test_nli_integration.py`)
- Full pipeline with mock `AsyncAnthropic` (fixed response fixture), real PostgreSQL + pgvector, real Neo4j
- `POST /query` returns `200` with valid `NLIResponse` schema
- `POST /query` with Neo4j down still returns `200` (degraded, no graph context)
- `POST /query` with `ANTHROPIC_API_KEY=""` returns `503`
- Rate limit: 11th request within 1 minute returns `429`

### Contract tests
- `NLIResponse` fields are always present (no optional fields missing from response)
- `source_device_ids` in Claude's JSON block are valid UUIDs matching returned `sources`
