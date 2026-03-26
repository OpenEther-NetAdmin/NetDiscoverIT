# Group 7 — NLI / RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `POST /api/v1/query` endpoint that answers plain-English network questions using a five-stage RAG pipeline: intent classification → pgvector retrieval → Neo4j graph traversal → context assembly → Claude synthesis.

**Architecture:** The question is embedded with all-mpnet-base-v2 and compared to precomputed domain centroid vectors to route to the correct pgvector column. If topology keywords are detected, Neo4j is queried for graph context. All context is assembled into a token-budgeted prompt and passed to Claude once per request.

**Tech Stack:** FastAPI (async), PostgreSQL + pgvector (cosine similarity), Neo4j (graph traversal), Anthropic SDK (`anthropic>=0.40.0`), `sentence-transformers>=2.7.0`, `tiktoken>=0.7.0`.

**Group 6a dependency:** Vector columns (`role_vector`, `topology_vector`, `security_vector`, `config_vector`) must be populated by the vectorizer. If they are NULL, the retriever returns empty results and Claude responds with "insufficient context in the network database". This is graceful degradation — the endpoint still works.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `services/api/app/services/nli/__init__.py` | Package export: `NLIService` |
| Create | `services/api/app/services/nli/intent_classifier.py` | Embed question → domain routing + graph flag |
| Create | `services/api/app/services/nli/vector_retriever.py` | pgvector cosine search per domain |
| Create | `services/api/app/services/nli/graph_traverser.py` | Neo4j queries for topology context |
| Create | `services/api/app/services/nli/context_builder.py` | Serialise retrieved data → token-budgeted prompt text |
| Create | `services/api/app/services/nli/claude_synthesizer.py` | Anthropic API call + confidence JSON extraction |
| Create | `services/api/app/services/nli/nli_service.py` | Orchestrator — runs stages 1–5 in sequence |
| Create | `services/api/app/api/routes/nli.py` | `POST /query` route |
| Create | `services/api/tests/api/test_nli_unit.py` | Unit tests for all NLI service components |
| Create | `services/api/tests/api/test_nli_integration.py` | Integration tests: full pipeline + error paths |
| Modify | `services/api/app/api/schemas.py` | Add `NLIQuery`, `NLISource`, `NLIResponse` |
| Modify | `services/api/app/core/config.py` | Add `NLI_VECTOR_TOP_K`, `NLI_RATE_LIMIT` |
| Modify | `services/api/requirements.txt` | Add `sentence-transformers`, `anthropic`, `tiktoken` |
| Modify | `services/api/app/api/routes/__init__.py` | Include `nli.router` |

---

## Task 1: Dependencies, Config, and Schemas

**Files:**
- Modify: `services/api/requirements.txt`
- Modify: `services/api/app/core/config.py`
- Modify: `services/api/app/api/schemas.py`

- [ ] **Step 1: Add Python dependencies to requirements.txt**

Open `services/api/requirements.txt` and add after the `slowapi` line:

```
# NLI / RAG
sentence-transformers==2.7.0
anthropic==0.40.0
tiktoken==0.7.0
```

- [ ] **Step 2: Add NLI config to config.py**

In `services/api/app/core/config.py`, add these two lines inside the `Settings` class, after the `RATE_LIMIT_READ` line:

```python
    # NLI / RAG
    NLI_VECTOR_TOP_K: int = 5      # devices retrieved per domain; clamped to 20 at runtime
    NLI_RATE_LIMIT: str = "10/minute"
```

- [ ] **Step 3: Add NLI schemas to schemas.py**

Open `services/api/app/api/schemas.py` and add at the end of the file:

```python
# ---------------------------------------------------------------------------
# NLI / RAG schemas
# ---------------------------------------------------------------------------

class NLIQuery(BaseModel):
    """Natural language query request"""
    question: str
    top_k: int = 5  # devices per domain; clamped to 20


class NLISource(BaseModel):
    """A device that contributed to the NLI answer"""
    device_id: str
    hostname: str
    similarity: float


class NLIResponse(BaseModel):
    """Natural language query response"""
    answer: str
    sources: list[NLISource]
    confidence: float         # 0.0–1.0 from Claude's self-assessment
    query_type: str           # topology | security | compliance | changes | inventory
    retrieved_device_count: int
    graph_traversal_used: bool
```

- [ ] **Step 4: Verify tests still pass**

```bash
cd /home/openether/NetDiscoverIT && make test
```

Expected: all 57 tests pass. Schema additions are purely additive.

- [ ] **Step 5: Commit**

```bash
cd /home/openether/NetDiscoverIT
git add services/api/requirements.txt \
        services/api/app/core/config.py \
        services/api/app/api/schemas.py
git commit -m "feat(nli): add NLI schemas, config, and dependencies (Group 7 Task 1)"
```

---

## Task 2: IntentClassifier

**Files:**
- Create: `services/api/app/services/nli/__init__.py`
- Create: `services/api/app/services/nli/intent_classifier.py`
- Modify: `services/api/tests/api/test_nli_unit.py`

### How it works

The classifier embeds the question using all-mpnet-base-v2, then computes cosine similarity against precomputed **domain centroids** — the mean vector of a small hardcoded set of seed phrases per domain. Domains whose similarity exceeds 0.30 are selected. A separate regex scan sets `needs_graph=True` if topology keywords are found.

Seed phrases (never change these without re-testing threshold):
- **inventory/role**: `"list all routers"`, `"how many devices"`, `"what vendor"`, `"device type"`, `"what kind of switch"`
- **topology**: `"what connects to"`, `"path from to"`, `"neighbors of"`, `"upstream device"`, `"directly connected"`
- **security**: `"telnet enabled"`, `"SSH disabled"`, `"open ports"`, `"security posture"`, `"SNMP community string"`
- **compliance**: `"PCI scope"`, `"HIPAA tagged"`, `"compliance devices"`, `"in scope for audit"`, `"compliance boundary"`
- **changes**: `"what changed"`, `"recent modifications"`, `"change record"`, `"configuration drift"`, `"modified last week"`

- [ ] **Step 1: Create package init**

Create `services/api/app/services/nli/__init__.py`:

```python
"""
NLI / RAG service package.
"""
from .nli_service import NLIService

__all__ = ["NLIService"]
```

- [ ] **Step 2: Write failing unit tests**

Create `services/api/tests/api/test_nli_unit.py`:

```python
"""
Unit tests for NLI service components.
All external dependencies (sentence-transformers, Anthropic, Neo4j) are mocked.
"""
import json
import pytest
from dataclasses import dataclass
from unittest.mock import MagicMock, AsyncMock, patch
import numpy as np


# ---------------------------------------------------------------------------
# IntentClassifier tests
# ---------------------------------------------------------------------------

class TestIntentClassifier:
    def _make_classifier(self, mock_model=None):
        """Return an IntentClassifier with the sentence-transformers model mocked."""
        with patch("app.services.nli.intent_classifier.SentenceTransformer") as MockST:
            if mock_model is None:
                mock_model = MagicMock()
                # encode() returns a fixed 768-dim vector
                mock_model.encode.return_value = np.ones(768, dtype=np.float32)
            MockST.return_value = mock_model
            from app.services.nli.intent_classifier import IntentClassifier
            return IntentClassifier()

    def test_topology_keywords_set_needs_graph(self):
        clf = self._make_classifier()
        intent = clf.classify("what connects to core-router-01?")
        assert intent.needs_graph is True

    def test_path_keyword_sets_needs_graph(self):
        clf = self._make_classifier()
        intent = clf.classify("show me the path from host-a to firewall-b")
        assert intent.needs_graph is True

    def test_security_question_no_graph(self):
        clf = self._make_classifier()
        intent = clf.classify("which devices have telnet enabled?")
        assert intent.needs_graph is False

    def test_ambiguous_question_uses_all_domains(self):
        """When no domain clears the similarity threshold, all 4 domains are selected."""
        mock_model = MagicMock()
        # Return a vector orthogonal to all centroids → near-zero similarity for all
        mock_model.encode.return_value = np.zeros(768, dtype=np.float32)
        clf = self._make_classifier(mock_model)
        intent = clf.classify("xyzzy frobulate the snorkel")
        assert len(intent.domains) == 4

    def test_extracted_entities_captures_ip(self):
        clf = self._make_classifier()
        intent = clf.classify("what connects to 192.168.1.1?")
        assert "192.168.1.1" in intent.extracted_entities

    def test_extracted_entities_captures_hostname(self):
        clf = self._make_classifier()
        intent = clf.classify("show neighbors of core-router-01")
        assert "core-router-01" in intent.extracted_entities
```

- [ ] **Step 3: Run test to confirm failure**

```bash
cd /home/openether/NetDiscoverIT
python -m pytest services/api/tests/api/test_nli_unit.py::TestIntentClassifier -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.nli.intent_classifier'`

- [ ] **Step 4: Create intent_classifier.py**

Create `services/api/app/services/nli/intent_classifier.py`:

```python
"""
NLI Intent Classifier

Embeds the user question and computes cosine similarity against precomputed domain
centroid vectors to route the query to the correct pgvector column(s). A separate
regex scan detects topology keywords and sets the needs_graph flag.
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import List

import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Model shared across all instances — loaded once at process startup
_MODEL: SentenceTransformer | None = None
MODEL_NAME = "all-mpnet-base-v2"

# Similarity threshold: domains above this score are selected
SIMILARITY_THRESHOLD = 0.30

# Topology keywords that trigger Neo4j graph traversal
_TOPOLOGY_PATTERN = re.compile(
    r"\b(connect|path|neighbor|upstream|downstream|hop|reach|next.hop|"
    r"adjacent|topology|link|interface|gateway|route.to)\b",
    re.IGNORECASE,
)

# Entity extraction: IPv4 addresses and kebab/dot hostnames
_IP_PATTERN = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_HOSTNAME_PATTERN = re.compile(r"\b[a-zA-Z][a-zA-Z0-9]*(?:[-\.][a-zA-Z0-9]+){1,}\b")

# Seed phrases per domain — centroids are computed from these at init time
_DOMAIN_SEEDS: dict[str, list[str]] = {
    "inventory": [
        "list all routers",
        "how many devices",
        "what vendor is this device",
        "device type",
        "what kind of switch",
        "show all network devices",
    ],
    "topology": [
        "what connects to this device",
        "path from host to firewall",
        "neighbors of core router",
        "upstream device",
        "directly connected interfaces",
        "network topology",
    ],
    "security": [
        "telnet enabled devices",
        "SSH is disabled",
        "open ports on device",
        "security posture",
        "SNMP community string configured",
        "which devices have HTTP enabled",
    ],
    "compliance": [
        "PCI scope devices",
        "HIPAA tagged network equipment",
        "compliance devices list",
        "in scope for audit",
        "compliance boundary devices",
        "SOC2 in scope",
    ],
    "changes": [
        "what changed last week",
        "recent configuration modifications",
        "change record for device",
        "configuration drift detected",
        "modified configuration",
        "unapproved changes",
    ],
}


@dataclass
class QueryIntent:
    domains: List[str]             # e.g. ["topology", "security"]
    needs_graph: bool
    extracted_entities: List[str]  # hostnames and IPs found in the question


def _get_model() -> SentenceTransformer:
    global _MODEL
    if _MODEL is None:
        logger.info("Loading sentence-transformers model: %s", MODEL_NAME)
        _MODEL = SentenceTransformer(MODEL_NAME)
    return _MODEL


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


class IntentClassifier:
    """Classifies a natural-language question into one or more retrieval domains."""

    def __init__(self) -> None:
        model = _get_model()
        # Precompute domain centroids from seed phrases
        self._centroids: dict[str, np.ndarray] = {}
        for domain, seeds in _DOMAIN_SEEDS.items():
            embeddings = model.encode(seeds, convert_to_numpy=True)
            self._centroids[domain] = embeddings.mean(axis=0)

    def classify(self, question: str) -> QueryIntent:
        model = _get_model()
        q_vec: np.ndarray = model.encode(question, convert_to_numpy=True)

        # Compute similarity to each domain centroid
        scores = {
            domain: _cosine_similarity(q_vec, centroid)
            for domain, centroid in self._centroids.items()
        }

        selected = [d for d, s in scores.items() if s >= SIMILARITY_THRESHOLD]

        # Fallback: ambiguous question → search all domains
        if not selected:
            selected = list(_DOMAIN_SEEDS.keys())
            logger.debug("No domain cleared threshold — using all domains. Scores: %s", scores)

        needs_graph = bool(_TOPOLOGY_PATTERN.search(question))

        # Extract entities (IPs + hostnames) from the question
        entities: list[str] = _IP_PATTERN.findall(question)
        for match in _HOSTNAME_PATTERN.finditer(question):
            token = match.group()
            # Filter out common English words that match the hostname pattern
            if len(token) > 4 and "-" in token or "." in token:
                entities.append(token)

        return QueryIntent(
            domains=selected,
            needs_graph=needs_graph,
            extracted_entities=entities,
        )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /home/openether/NetDiscoverIT
python -m pytest services/api/tests/api/test_nli_unit.py::TestIntentClassifier -v
```

Expected: all 6 tests pass.

- [ ] **Step 6: Run full test suite to confirm nothing broken**

```bash
make test
```

Expected: all 57 tests pass (6 new NLI unit tests + 57 existing = 63 total).

- [ ] **Step 7: Commit**

```bash
git add services/api/app/services/nli/ \
        services/api/tests/api/test_nli_unit.py
git commit -m "feat(nli): add IntentClassifier with embedding + keyword routing (Group 7 Task 2)"
```

---

## Task 3: VectorRetriever

**Files:**
- Create: `services/api/app/services/nli/vector_retriever.py`
- Modify: `services/api/tests/api/test_nli_unit.py`

### How it works

Executes async pgvector cosine-distance queries. The domain name determines which column is searched. For `changes` and `compliance` domains, additional enrichment queries pull related `ChangeRecord` / `AlertEvent` rows for matched devices.

- [ ] **Step 1: Write failing unit tests**

Append to `services/api/tests/api/test_nli_unit.py`:

```python
# ---------------------------------------------------------------------------
# VectorRetriever tests
# ---------------------------------------------------------------------------

class TestVectorRetriever:
    def _make_retriever(self):
        from app.services.nli.vector_retriever import VectorRetriever
        return VectorRetriever()

    def test_domain_to_column_mapping(self):
        from app.services.nli.vector_retriever import DOMAIN_COLUMN_MAP
        assert DOMAIN_COLUMN_MAP["topology"] == "topology_vector"
        assert DOMAIN_COLUMN_MAP["security"] == "security_vector"
        assert DOMAIN_COLUMN_MAP["compliance"] == "role_vector"
        assert DOMAIN_COLUMN_MAP["changes"] == "config_vector"
        assert DOMAIN_COLUMN_MAP["inventory"] == "role_vector"

    def test_top_k_clamped_to_20(self):
        from app.services.nli.vector_retriever import VectorRetriever
        r = VectorRetriever()
        assert r._clamp_top_k(100) == 20
        assert r._clamp_top_k(5) == 5
        assert r._clamp_top_k(0) == 1

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_vectors(self):
        """Devices with NULL vectors return empty results (graceful Group 6a degradation)."""
        from app.services.nli.vector_retriever import VectorRetriever, DeviceContext
        r = VectorRetriever()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        import numpy as np
        results = await r.retrieve(
            db=mock_db,
            org_id="00000000-0000-0000-0000-000000000001",
            domain="security",
            query_vec=np.ones(768, dtype=np.float32),
            top_k=5,
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_returns_device_context_on_match(self):
        from app.services.nli.vector_retriever import VectorRetriever, DeviceContext
        r = VectorRetriever()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            MagicMock(
                id="uuid-1",
                hostname="core-router-01",
                vendor="Cisco",
                device_type="router",
                metadata={"security_posture": {"ssh_enabled": True, "telnet_enabled": False}},
                compliance_scope=["PCI-BOUNDARY"],
                similarity=0.91,
            )
        ]
        mock_db.execute = AsyncMock(return_value=mock_result)

        import numpy as np
        results = await r.retrieve(
            db=mock_db,
            org_id="00000000-0000-0000-0000-000000000001",
            domain="security",
            query_vec=np.ones(768, dtype=np.float32),
            top_k=5,
        )
        assert len(results) == 1
        assert results[0].device_id == "uuid-1"
        assert results[0].hostname == "core-router-01"
        assert results[0].similarity == pytest.approx(0.91)
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
python -m pytest services/api/tests/api/test_nli_unit.py::TestVectorRetriever -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.nli.vector_retriever'`

- [ ] **Step 3: Create vector_retriever.py**

Create `services/api/app/services/nli/vector_retriever.py`:

```python
"""
NLI Vector Retriever

Executes pgvector cosine-distance queries to find the most relevant devices
for a given query embedding and domain. Uses raw SQL for pgvector operators.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Domain → Device vector column
DOMAIN_COLUMN_MAP: dict[str, str] = {
    "inventory": "role_vector",
    "topology": "topology_vector",
    "security": "security_vector",
    "compliance": "role_vector",
    "changes": "config_vector",
}

MAX_TOP_K = 20


@dataclass
class DeviceContext:
    device_id: str
    hostname: str
    vendor: Optional[str]
    device_type: Optional[str]
    metadata: dict
    compliance_scope: list[str]
    similarity: float
    # Enrichment — populated for changes/security domains
    recent_changes: list[dict] = field(default_factory=list)
    recent_alerts: list[dict] = field(default_factory=list)


class VectorRetriever:
    """Retrieves relevant devices from pgvector for a given domain and query embedding."""

    def _clamp_top_k(self, top_k: int) -> int:
        return max(1, min(top_k, MAX_TOP_K))

    async def retrieve(
        self,
        db: AsyncSession,
        org_id: str,
        domain: str,
        query_vec: np.ndarray,
        top_k: int = 5,
    ) -> List[DeviceContext]:
        column = DOMAIN_COLUMN_MAP.get(domain, "role_vector")
        k = self._clamp_top_k(top_k)
        vec_str = json.dumps(query_vec.tolist())

        sql = text(f"""
            SELECT id, hostname, vendor, device_type, metadata, compliance_scope,
                   1 - ({column} <=> :query_vec::vector) AS similarity
            FROM devices
            WHERE organization_id = :org_id
              AND {column} IS NOT NULL
            ORDER BY {column} <=> :query_vec::vector
            LIMIT :k
        """)  # noqa: S608 — column name comes from DOMAIN_COLUMN_MAP, not user input

        result = await db.execute(sql, {"query_vec": vec_str, "org_id": org_id, "k": k})
        rows = result.fetchall()

        if not rows:
            logger.debug("VectorRetriever: no results for domain=%s org=%s", domain, org_id)
            return []

        devices = [
            DeviceContext(
                device_id=str(row.id),
                hostname=row.hostname or str(row.id),
                vendor=row.vendor,
                device_type=row.device_type,
                metadata=row.metadata or {},
                compliance_scope=row.compliance_scope or [],
                similarity=float(row.similarity),
            )
            for row in rows
        ]

        # Domain-specific enrichment
        device_ids = [d.device_id for d in devices]
        if domain == "changes":
            await self._enrich_changes(db, devices, device_ids)
        elif domain == "security":
            await self._enrich_alerts(db, devices, device_ids)

        return devices

    async def _enrich_changes(
        self, db: AsyncSession, devices: list[DeviceContext], device_ids: list[str]
    ) -> None:
        """Attach recent ChangeRecord summaries to matched devices."""
        if not device_ids:
            return
        sql = text("""
            SELECT change_number, status, risk_level, description,
                   requested_at, affected_devices
            FROM change_records
            WHERE organization_id IN (
                SELECT organization_id FROM devices WHERE id = ANY(:ids::uuid[])
            )
            AND :ids::uuid[] && affected_devices::uuid[]
            AND requested_at >= NOW() - INTERVAL '90 days'
            ORDER BY requested_at DESC
            LIMIT 20
        """)
        try:
            result = await db.execute(sql, {"ids": device_ids})
            rows = result.fetchall()
        except Exception:
            logger.warning("VectorRetriever: change enrichment query failed", exc_info=True)
            return

        # Attach changes to relevant devices
        for row in rows:
            affected = row.affected_devices or []
            summary = {
                "change_number": row.change_number,
                "status": row.status,
                "risk_level": row.risk_level,
                "description": row.description,
                "requested_at": str(row.requested_at),
            }
            for device in devices:
                if device.device_id in [str(d) for d in affected]:
                    device.recent_changes.append(summary)

    async def _enrich_alerts(
        self, db: AsyncSession, devices: list[DeviceContext], device_ids: list[str]
    ) -> None:
        """Attach recent AlertEvent summaries to matched devices."""
        if not device_ids:
            return
        sql = text("""
            SELECT ae.device_id, ar.name, ar.rule_type, ae.severity,
                   ae.message, ae.triggered_at
            FROM alert_events ae
            JOIN alert_rules ar ON ar.id = ae.rule_id
            WHERE ae.device_id = ANY(:ids::uuid[])
            AND ae.triggered_at >= NOW() - INTERVAL '30 days'
            ORDER BY ae.triggered_at DESC
            LIMIT 30
        """)
        try:
            result = await db.execute(sql, {"ids": device_ids})
            rows = result.fetchall()
        except Exception:
            logger.warning("VectorRetriever: alert enrichment query failed", exc_info=True)
            return

        by_device: dict[str, list[dict]] = {}
        for row in rows:
            key = str(row.device_id)
            by_device.setdefault(key, []).append({
                "rule_name": row.name,
                "rule_type": row.rule_type,
                "severity": row.severity,
                "message": row.message,
                "triggered_at": str(row.triggered_at),
            })

        for device in devices:
            device.recent_alerts = by_device.get(device.device_id, [])
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest services/api/tests/api/test_nli_unit.py::TestVectorRetriever -v
```

Expected: all 4 tests pass.

- [ ] **Step 5: Run full suite**

```bash
make test
```

Expected: all previous tests still pass.

- [ ] **Step 6: Commit**

```bash
git add services/api/app/services/nli/vector_retriever.py \
        services/api/tests/api/test_nli_unit.py
git commit -m "feat(nli): add VectorRetriever with pgvector cosine search (Group 7 Task 3)"
```

---

## Task 4: GraphTraverser

**Files:**
- Create: `services/api/app/services/nli/graph_traverser.py`
- Modify: `services/api/tests/api/test_nli_unit.py`

### How it works

Wraps the existing `Neo4jClient`. Detects the query shape from keywords in the question, selects an anchor device from the vector retriever results (highest similarity, or by hostname match against `extracted_entities`), then runs one of three Cypher patterns.

- [ ] **Step 1: Write failing unit tests**

Append to `services/api/tests/api/test_nli_unit.py`:

```python
# ---------------------------------------------------------------------------
# GraphTraverser tests
# ---------------------------------------------------------------------------

class TestGraphTraverser:
    def _make_traverser(self):
        from app.services.nli.graph_traverser import GraphTraverser
        return GraphTraverser()

    def test_neighborhood_shape_selected_for_connects_to(self):
        from app.services.nli.graph_traverser import GraphTraverser, QueryShape
        t = GraphTraverser()
        shape = t._detect_shape("what connects to core-router-01?")
        assert shape == QueryShape.NEIGHBORHOOD

    def test_path_shape_selected_for_path_from(self):
        from app.services.nli.graph_traverser import GraphTraverser, QueryShape
        t = GraphTraverser()
        shape = t._detect_shape("show path from host-a to firewall-b")
        assert shape == QueryShape.PATH

    def test_vlan_shape_selected_for_segment_keywords(self):
        from app.services.nli.graph_traverser import GraphTraverser, QueryShape
        t = GraphTraverser()
        shape = t._detect_shape("what devices are in the same VLAN as core-sw-01?")
        assert shape == QueryShape.VLAN

    def test_neighborhood_is_default_shape(self):
        from app.services.nli.graph_traverser import GraphTraverser, QueryShape
        t = GraphTraverser()
        shape = t._detect_shape("what is upstream of this device")
        assert shape == QueryShape.NEIGHBORHOOD

    @pytest.mark.asyncio
    async def test_returns_none_when_neo4j_unavailable(self):
        from app.services.nli.graph_traverser import GraphTraverser
        from app.services.nli.vector_retriever import DeviceContext
        t = GraphTraverser()

        # No Neo4j client provided
        result = await t.traverse(
            neo4j_client=None,
            question="what connects to core-router-01?",
            anchor_devices=[
                DeviceContext(
                    device_id="uuid-1",
                    hostname="core-router-01",
                    vendor="Cisco",
                    device_type="router",
                    metadata={},
                    compliance_scope=[],
                    similarity=0.91,
                )
            ],
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_neo4j_exception(self):
        from app.services.nli.graph_traverser import GraphTraverser
        from app.services.nli.vector_retriever import DeviceContext
        t = GraphTraverser()

        mock_client = AsyncMock()
        mock_client.get_device_neighborhood = AsyncMock(side_effect=RuntimeError("connection refused"))

        result = await t.traverse(
            neo4j_client=mock_client,
            question="what connects to core-router-01?",
            anchor_devices=[
                DeviceContext(
                    device_id="uuid-1",
                    hostname="core-router-01",
                    vendor="Cisco",
                    device_type="router",
                    metadata={},
                    compliance_scope=[],
                    similarity=0.91,
                )
            ],
        )
        assert result is None
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
python -m pytest services/api/tests/api/test_nli_unit.py::TestGraphTraverser -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.nli.graph_traverser'`

- [ ] **Step 3: Create graph_traverser.py**

Create `services/api/app/services/nli/graph_traverser.py`:

```python
"""
NLI Graph Traverser

Wraps Neo4jClient to provide three query shapes for topology context retrieval:
neighborhood (2-hop), path (shortestPath), and VLAN segmentation.
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

logger = logging.getLogger(__name__)

_PATH_PATTERN = re.compile(r"\b(path from|route from|trace from|hop from)\b", re.IGNORECASE)
_VLAN_PATTERN = re.compile(r"\b(vlan|segment|same network|broadcast domain)\b", re.IGNORECASE)


class QueryShape(str, Enum):
    NEIGHBORHOOD = "neighborhood"
    PATH = "path"
    VLAN = "vlan"


@dataclass
class GraphContext:
    nodes: List[dict] = field(default_factory=list)
    edges: List[dict] = field(default_factory=list)
    path: Optional[List[str]] = None
    query_shape: str = QueryShape.NEIGHBORHOOD


class GraphTraverser:
    """Executes topology queries against Neo4j for NLI context enrichment."""

    def _detect_shape(self, question: str) -> QueryShape:
        if _PATH_PATTERN.search(question):
            return QueryShape.PATH
        if _VLAN_PATTERN.search(question):
            return QueryShape.VLAN
        return QueryShape.NEIGHBORHOOD

    def _pick_anchor(self, anchor_devices, extracted_entities: list[str]) -> Optional[str]:
        """Return hostname of the best anchor device."""
        if not anchor_devices:
            return None
        # Try to match an extracted entity to a device hostname
        for entity in extracted_entities:
            for device in anchor_devices:
                if entity.lower() in device.hostname.lower():
                    return device.hostname
        # Fall back to highest-similarity device
        return anchor_devices[0].hostname

    async def traverse(
        self,
        neo4j_client,
        question: str,
        anchor_devices,
        extracted_entities: list[str] | None = None,
    ) -> Optional[GraphContext]:
        """Run a graph query. Returns None if Neo4j is unavailable or the query fails."""
        if neo4j_client is None:
            return None

        shape = self._detect_shape(question)
        entities = extracted_entities or []
        anchor = self._pick_anchor(anchor_devices, entities)
        if not anchor:
            return None

        try:
            if shape == QueryShape.PATH:
                return await self._run_path_query(neo4j_client, anchor, entities)
            elif shape == QueryShape.VLAN:
                return await self._run_vlan_query(neo4j_client, anchor)
            else:
                return await self._run_neighborhood_query(neo4j_client, anchor)
        except Exception:
            logger.warning("GraphTraverser: query failed (Neo4j unavailable?)", exc_info=True)
            return None

    async def _run_neighborhood_query(self, client, anchor: str) -> GraphContext:
        """2-hop neighborhood from anchor device."""
        async with client._driver.session() as session:
            result = await session.run(
                """
                MATCH (d:Device {hostname: $hostname})-[r*1..2]-(neighbor)
                RETURN d, r, neighbor
                LIMIT 50
                """,
                {"hostname": anchor},
            )
            records = await result.data()

        nodes = []
        edges = []
        seen_nodes: set[str] = set()
        for record in records:
            for key in ("d", "neighbor"):
                node = dict(record.get(key, {}))
                node_id = node.get("id") or node.get("hostname", "")
                if node_id and node_id not in seen_nodes:
                    nodes.append(node)
                    seen_nodes.add(node_id)
            for rel in record.get("r", []):
                edges.append({
                    "type": rel.type if hasattr(rel, "type") else str(rel),
                    "start": rel.start_node.get("hostname", "") if hasattr(rel, "start_node") else "",
                    "end": rel.end_node.get("hostname", "") if hasattr(rel, "end_node") else "",
                })
        return GraphContext(nodes=nodes, edges=edges, query_shape=QueryShape.NEIGHBORHOOD)

    async def _run_path_query(
        self, client, anchor: str, entities: list[str]
    ) -> GraphContext:
        """shortestPath between two devices."""
        # Try to find a second device in extracted entities
        target = next(
            (e for e in entities if e.lower() != anchor.lower()), None
        )
        if not target:
            # Fall back to neighborhood if we can't find a target
            return await self._run_neighborhood_query(client, anchor)

        async with client._driver.session() as session:
            result = await session.run(
                """
                MATCH (a:Device {hostname: $from}), (b:Device {hostname: $to}),
                      p = shortestPath((a)-[*]-(b))
                RETURN [node in nodes(p) | node.hostname] AS path_hostnames
                """,
                {"from": anchor, "to": target},
            )
            records = await result.data()

        path = records[0]["path_hostnames"] if records else []
        return GraphContext(path=path, query_shape=QueryShape.PATH)

    async def _run_vlan_query(self, client, anchor: str) -> GraphContext:
        """Find devices in the same VLAN as anchor."""
        async with client._driver.session() as session:
            result = await session.run(
                """
                MATCH (d:Device {hostname: $hostname})-[:HAS_INTERFACE]->(:Interface)
                      -[:MEMBER_OF]->(v:VLAN)<-[:MEMBER_OF]-(:Interface)
                      <-[:HAS_INTERFACE]-(peer:Device)
                RETURN d, v, peer
                LIMIT 50
                """,
                {"hostname": anchor},
            )
            records = await result.data()

        nodes = []
        seen: set[str] = set()
        for record in records:
            for key in ("d", "peer"):
                node = dict(record.get(key, {}))
                h = node.get("hostname", "")
                if h and h not in seen:
                    nodes.append(node)
                    seen.add(h)
        return GraphContext(nodes=nodes, query_shape=QueryShape.VLAN)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest services/api/tests/api/test_nli_unit.py::TestGraphTraverser -v
```

Expected: all 6 tests pass.

- [ ] **Step 5: Run full suite**

```bash
make test
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add services/api/app/services/nli/graph_traverser.py \
        services/api/tests/api/test_nli_unit.py
git commit -m "feat(nli): add GraphTraverser for Neo4j topology context (Group 7 Task 4)"
```

---

## Task 5: ContextBuilder

**Files:**
- Create: `services/api/app/services/nli/context_builder.py`
- Modify: `services/api/tests/api/test_nli_unit.py`

### How it works

Serialises `List[DeviceContext]` and `Optional[GraphContext]` into a human-readable prompt block. Uses `tiktoken` to count tokens and truncates at 8,000 tokens by progressively dropping low-priority data.

- [ ] **Step 1: Write failing unit tests**

Append to `services/api/tests/api/test_nli_unit.py`:

```python
# ---------------------------------------------------------------------------
# ContextBuilder tests
# ---------------------------------------------------------------------------

class TestContextBuilder:
    def _make_builder(self):
        from app.services.nli.context_builder import ContextBuilder
        return ContextBuilder()

    def _make_device(self, hostname="core-router-01", similarity=0.91):
        from app.services.nli.vector_retriever import DeviceContext
        return DeviceContext(
            device_id="uuid-1",
            hostname=hostname,
            vendor="Cisco",
            device_type="router",
            metadata={
                "security_posture": {
                    "ssh_enabled": True,
                    "telnet_enabled": False,
                    "http_enabled": False,
                    "snmp_enabled": True,
                },
                "inferred_role": "core_router",
                "role_confidence": 0.95,
            },
            compliance_scope=["PCI-BOUNDARY"],
            similarity=similarity,
        )

    def test_builds_non_empty_context(self):
        builder = self._make_builder()
        context, sources = builder.build([self._make_device()], None)
        assert len(context) > 0
        assert "core-router-01" in context

    def test_sources_list_populated(self):
        builder = self._make_builder()
        _, sources = builder.build([self._make_device()], None)
        assert len(sources) == 1
        assert sources[0].device_id == "uuid-1"
        assert sources[0].hostname == "core-router-01"
        assert sources[0].similarity == pytest.approx(0.91)

    def test_empty_devices_returns_no_context_found(self):
        builder = self._make_builder()
        context, sources = builder.build([], None)
        assert "no matching devices" in context.lower()
        assert sources == []

    def test_graph_context_included_when_provided(self):
        from app.services.nli.graph_traverser import GraphContext, QueryShape
        builder = self._make_builder()
        graph = GraphContext(
            nodes=[{"hostname": "core-router-01"}, {"hostname": "edge-fw-01"}],
            edges=[{"type": "CONNECTED_TO", "start": "core-router-01", "end": "edge-fw-01"}],
            query_shape=QueryShape.NEIGHBORHOOD,
        )
        context, _ = builder.build([self._make_device()], graph)
        assert "TOPOLOGY" in context
        assert "edge-fw-01" in context

    def test_token_count_under_budget(self):
        builder = self._make_builder()
        # 20 devices should still fit under 8k tokens
        devices = [self._make_device(hostname=f"sw-{i:02d}", similarity=0.9 - i * 0.01) for i in range(20)]
        context, _ = builder.build(devices, None)
        token_count = builder._count_tokens(context)
        assert token_count <= 8000
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
python -m pytest services/api/tests/api/test_nli_unit.py::TestContextBuilder -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.nli.context_builder'`

- [ ] **Step 3: Create context_builder.py**

Create `services/api/app/services/nli/context_builder.py`:

```python
"""
NLI Context Builder

Serialises retrieved device and graph data into a token-budgeted prompt context block.
Truncation order (lowest priority first): change record details, graph edges, device metadata fields.
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import tiktoken

from app.services.nli.vector_retriever import DeviceContext
from app.services.nli.graph_traverser import GraphContext, QueryShape
from app.api.schemas import NLISource

logger = logging.getLogger(__name__)

TOKEN_BUDGET = 8_000
_ENCODING = tiktoken.get_encoding("cl100k_base")


class ContextBuilder:
    """Converts retrieved device + graph data into a prompt-ready text block."""

    def _count_tokens(self, text: str) -> int:
        return len(_ENCODING.encode(text))

    def _format_device(self, d: DeviceContext, include_changes: bool = True) -> str:
        sp = d.metadata.get("security_posture", {})
        role = d.metadata.get("inferred_role", d.device_type or "unknown")
        confidence = d.metadata.get("role_confidence")
        role_str = f"{role} (confidence: {confidence:.0%})" if confidence else role

        lines = [
            f"Device: {d.hostname}",
            f"  Vendor: {d.vendor or 'unknown'} | Type: {d.device_type or 'unknown'} | Role: {role_str}",
        ]

        if sp:
            ssh = "enabled" if sp.get("ssh_enabled") else "disabled"
            telnet = "enabled" if sp.get("telnet_enabled") else "disabled"
            snmp = "enabled" if sp.get("snmp_enabled") else "disabled"
            http = "enabled" if sp.get("http_enabled") else "disabled"
            lines.append(f"  Security: SSH={ssh}, Telnet={telnet}, SNMP={snmp}, HTTP={http}")

        if d.compliance_scope:
            lines.append(f"  Compliance scope: {', '.join(d.compliance_scope)}")

        lines.append(f"  [Source: {d.device_type or 'device'} similarity={d.similarity:.2f}]")

        if include_changes and d.recent_changes:
            lines.append(f"  Recent changes ({len(d.recent_changes)}):")
            for c in d.recent_changes[:3]:
                lines.append(
                    f"    - {c['change_number']} | {c['status']} | {c.get('description', '')[:60]}"
                )

        if d.recent_alerts:
            lines.append(f"  Recent alerts ({len(d.recent_alerts)}):")
            for a in d.recent_alerts[:3]:
                lines.append(f"    - [{a['severity']}] {a['message'][:60]}")

        return "\n".join(lines)

    def _format_graph(self, graph: GraphContext, include_edges: bool = True) -> str:
        lines = ["\n=== TOPOLOGY ==="]
        if graph.path:
            lines.append("Path: " + " --> ".join(graph.path))
        for node in graph.nodes[:30]:
            hostname = node.get("hostname") or node.get("id", "?")
            lines.append(f"  Node: {hostname}")
        if include_edges:
            for edge in graph.edges[:20]:
                lines.append(
                    f"  {edge.get('start', '?')} --{edge.get('type', '?')}--> {edge.get('end', '?')}"
                )
        return "\n".join(lines)

    def build(
        self,
        devices: List[DeviceContext],
        graph: Optional[GraphContext],
    ) -> Tuple[str, List[NLISource]]:
        """
        Build prompt context from retrieved devices and optional graph context.

        Returns:
            (context_text, sources_list)
        """
        if not devices:
            return "No matching devices found in the network database.", []

        sources = [
            NLISource(
                device_id=d.device_id,
                hostname=d.hostname,
                similarity=d.similarity,
            )
            for d in devices
        ]

        # Build full context and check token budget
        device_block = "\n=== NETWORK CONTEXT ===\n"
        device_block += "\n\n".join(
            self._format_device(d, include_changes=True) for d in devices
        )

        graph_block = self._format_graph(graph, include_edges=True) if graph else ""
        full_context = device_block + graph_block

        if self._count_tokens(full_context) <= TOKEN_BUDGET:
            return full_context, sources

        # Truncation pass 1: drop change details
        device_block = "\n=== NETWORK CONTEXT ===\n"
        device_block += "\n\n".join(
            self._format_device(d, include_changes=False) for d in devices
        )
        graph_block = self._format_graph(graph, include_edges=True) if graph else ""
        full_context = device_block + graph_block

        if self._count_tokens(full_context) <= TOKEN_BUDGET:
            logger.debug("ContextBuilder: truncated change details to fit token budget")
            return full_context, sources

        # Truncation pass 2: drop graph edges
        graph_block = self._format_graph(graph, include_edges=False) if graph else ""
        full_context = device_block + graph_block

        if self._count_tokens(full_context) <= TOKEN_BUDGET:
            logger.debug("ContextBuilder: truncated graph edges to fit token budget")
            return full_context, sources

        # Truncation pass 3: trim to fewest devices that fit
        for n in range(len(devices) - 1, 0, -1):
            device_block = "\n=== NETWORK CONTEXT ===\n"
            device_block += "\n\n".join(
                self._format_device(d, include_changes=False) for d in devices[:n]
            )
            full_context = device_block
            if self._count_tokens(full_context) <= TOKEN_BUDGET:
                logger.warning(
                    "ContextBuilder: reduced to %d devices to fit token budget", n
                )
                return full_context, sources[:n]

        # Absolute fallback: first device only
        return self._format_device(devices[0], include_changes=False), sources[:1]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest services/api/tests/api/test_nli_unit.py::TestContextBuilder -v
```

Expected: all 5 tests pass.

- [ ] **Step 5: Run full suite**

```bash
make test
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add services/api/app/services/nli/context_builder.py \
        services/api/tests/api/test_nli_unit.py
git commit -m "feat(nli): add ContextBuilder with token-budgeted prompt serialisation (Group 7 Task 5)"
```

---

## Task 6: ClaudeSynthesizer

**Files:**
- Create: `services/api/app/services/nli/claude_synthesizer.py`
- Modify: `services/api/tests/api/test_nli_unit.py`

### How it works

Makes a single async Anthropic API call. Claude is instructed to append a JSON confidence block as the last line of its response. The synthesizer extracts this block; if it's malformed, confidence defaults to 0.5.

- [ ] **Step 1: Write failing unit tests**

Append to `services/api/tests/api/test_nli_unit.py`:

```python
# ---------------------------------------------------------------------------
# ClaudeSynthesizer tests
# ---------------------------------------------------------------------------

class TestClaudeSynthesizer:
    def _make_synthesizer(self, api_key="test-key"):
        with patch("app.services.nli.claude_synthesizer.AsyncAnthropic"):
            from app.services.nli.claude_synthesizer import ClaudeSynthesizer
            return ClaudeSynthesizer(api_key=api_key, model="claude-sonnet-4-6")

    def test_available_false_when_no_api_key(self):
        from app.services.nli.claude_synthesizer import ClaudeSynthesizer
        with patch("app.services.nli.claude_synthesizer.AsyncAnthropic"):
            s = ClaudeSynthesizer(api_key="", model="claude-sonnet-4-6")
        assert s.available is False

    def test_available_true_when_api_key_set(self):
        s = self._make_synthesizer(api_key="sk-ant-test")
        assert s.available is True

    def test_parse_confidence_json_valid(self):
        s = self._make_synthesizer()
        answer, confidence, query_type, source_ids = s._parse_response(
            'Three devices have Telnet enabled.\n'
            '{"confidence": 0.92, "query_type": "security", "source_device_ids": ["uuid-1", "uuid-2"]}'
        )
        assert answer == "Three devices have Telnet enabled."
        assert confidence == pytest.approx(0.92)
        assert query_type == "security"
        assert source_ids == ["uuid-1", "uuid-2"]

    def test_parse_confidence_json_malformed_falls_back(self):
        s = self._make_synthesizer()
        answer, confidence, query_type, source_ids = s._parse_response(
            "Some answer without a JSON block."
        )
        assert answer == "Some answer without a JSON block."
        assert confidence == pytest.approx(0.5)
        assert query_type == "inventory"
        assert source_ids == []

    def test_parse_confidence_clamped_to_0_1(self):
        s = self._make_synthesizer()
        _, confidence, _, _ = s._parse_response(
            'Answer.\n{"confidence": 1.5, "query_type": "security", "source_device_ids": []}'
        )
        assert confidence <= 1.0

    @pytest.mark.asyncio
    async def test_synthesize_calls_anthropic_and_returns_parsed(self):
        with patch("app.services.nli.claude_synthesizer.AsyncAnthropic") as MockClient:
            mock_instance = MagicMock()
            MockClient.return_value = mock_instance
            mock_instance.messages = MagicMock()
            mock_instance.messages.create = AsyncMock(return_value=MagicMock(
                content=[MagicMock(text=(
                    'Three devices have Telnet enabled: sw-01, sw-02, sw-03.\n'
                    '{"confidence": 0.90, "query_type": "security", "source_device_ids": ["uuid-1"]}'
                ))]
            ))

            from importlib import reload
            import app.services.nli.claude_synthesizer as cs_module
            reload(cs_module)
            synth = cs_module.ClaudeSynthesizer(api_key="sk-test", model="claude-sonnet-4-6")

            result = await synth.synthesize(
                question="Which devices have Telnet?",
                context="=== NETWORK CONTEXT ===\nDevice: sw-01\n...",
            )

        assert "Telnet" in result.answer
        assert result.confidence == pytest.approx(0.90)
        assert result.query_type == "security"
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
python -m pytest services/api/tests/api/test_nli_unit.py::TestClaudeSynthesizer -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.nli.claude_synthesizer'`

- [ ] **Step 3: Create claude_synthesizer.py**

Create `services/api/app/services/nli/claude_synthesizer.py`:

```python
"""
NLI Claude Synthesizer

Makes a single async Anthropic API call with the assembled context and user question.
Extracts a structured JSON confidence block from Claude's response.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a network documentation assistant for NetDiscoverIT.
Answer questions using ONLY the provided network context below. Cite device hostnames when relevant.
If the context does not contain enough information to answer, say so explicitly — never invent device names or facts.
Keep answers concise (2–5 sentences unless a list is clearly more useful).

IMPORTANT: End every response with a JSON block on the very last line, with no trailing text:
{"confidence": <float 0.0-1.0>, "query_type": "<topology|security|compliance|changes|inventory>", "source_device_ids": ["<uuid>", ...]}

The confidence should reflect how well the context supports your answer (1.0 = fully supported, 0.0 = no relevant data).
The source_device_ids should list UUIDs of devices you cited in your answer."""

API_TIMEOUT = 15.0  # seconds


@dataclass
class SynthesisResult:
    answer: str
    confidence: float
    query_type: str
    source_device_ids: List[str]


class ClaudeSynthesizer:
    """Wraps the Anthropic API for single-call NLI synthesis."""

    def __init__(self, api_key: str, model: str) -> None:
        self.model = model
        self.available = bool(api_key)
        if self.available:
            self._client = AsyncAnthropic(api_key=api_key)

    def _parse_response(self, text: str) -> Tuple[str, float, str, List[str]]:
        """
        Extract answer text and JSON confidence block from Claude's response.
        The JSON block is expected to be the last line of the response.
        Falls back to confidence=0.5, query_type="inventory", source_ids=[] on parse failure.
        """
        lines = text.strip().split("\n")
        json_block = None

        # Try last line first
        for candidate in reversed(lines):
            candidate = candidate.strip()
            if candidate.startswith("{") and candidate.endswith("}"):
                try:
                    json_block = json.loads(candidate)
                    answer_lines = [l for l in lines if l.strip() != candidate]
                    break
                except json.JSONDecodeError:
                    continue

        if json_block is None:
            return text.strip(), 0.5, "inventory", []

        answer = "\n".join(answer_lines).strip()
        confidence = min(1.0, max(0.0, float(json_block.get("confidence", 0.5))))
        query_type = json_block.get("query_type", "inventory")
        source_ids = json_block.get("source_device_ids", [])

        return answer, confidence, query_type, source_ids

    async def synthesize(self, question: str, context: str) -> SynthesisResult:
        """
        Call Claude with the assembled context and return a structured synthesis result.
        Caller must check `self.available` before calling.
        """
        user_message = f"Network context:\n{context}\n\nQuestion: {question}"

        response = await self._client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            timeout=API_TIMEOUT,
        )

        raw_text = response.content[0].text
        answer, confidence, query_type, source_ids = self._parse_response(raw_text)

        return SynthesisResult(
            answer=answer,
            confidence=confidence,
            query_type=query_type,
            source_device_ids=source_ids,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest services/api/tests/api/test_nli_unit.py::TestClaudeSynthesizer -v
```

Expected: all 6 tests pass.

- [ ] **Step 5: Run full suite**

```bash
make test
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add services/api/app/services/nli/claude_synthesizer.py \
        services/api/tests/api/test_nli_unit.py
git commit -m "feat(nli): add ClaudeSynthesizer with confidence JSON extraction (Group 7 Task 6)"
```

---

## Task 7: NLIService Orchestrator + Route

**Files:**
- Create: `services/api/app/services/nli/nli_service.py`
- Create: `services/api/app/api/routes/nli.py`
- Modify: `services/api/app/api/routes/__init__.py`
- Modify: `services/api/tests/api/test_nli_unit.py`

- [ ] **Step 1: Write failing orchestrator unit tests**

Append to `services/api/tests/api/test_nli_unit.py`:

```python
# ---------------------------------------------------------------------------
# NLIService orchestrator tests
# ---------------------------------------------------------------------------

class TestNLIService:
    def _make_service(self, api_key="sk-test"):
        with patch("app.services.nli.intent_classifier.SentenceTransformer"), \
             patch("app.services.nli.claude_synthesizer.AsyncAnthropic"):
            from app.services.nli.nli_service import NLIService
            return NLIService(api_key=api_key, model="claude-sonnet-4-6")

    def test_service_unavailable_when_no_api_key(self):
        with patch("app.services.nli.intent_classifier.SentenceTransformer"), \
             patch("app.services.nli.claude_synthesizer.AsyncAnthropic"):
            from app.services.nli.nli_service import NLIService
            svc = NLIService(api_key="", model="claude-sonnet-4-6")
        assert svc.available is False

    def test_service_available_when_api_key_set(self):
        svc = self._make_service()
        assert svc.available is True

    @pytest.mark.asyncio
    async def test_query_returns_nli_response(self):
        from app.services.nli.nli_service import NLIService
        from app.api.schemas import NLIResponse

        with patch("app.services.nli.intent_classifier.SentenceTransformer") as MockST, \
             patch("app.services.nli.claude_synthesizer.AsyncAnthropic"):
            mock_model = MagicMock()
            mock_model.encode.return_value = np.ones(768, dtype=np.float32)
            MockST.return_value = mock_model
            svc = NLIService(api_key="sk-test", model="claude-sonnet-4-6")

        mock_db = AsyncMock()
        # VectorRetriever returns empty (no vectors populated — graceful degradation)
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Patch ClaudeSynthesizer.synthesize
        from app.services.nli.claude_synthesizer import SynthesisResult
        svc._synthesizer.synthesize = AsyncMock(return_value=SynthesisResult(
            answer="No matching devices found in the network database.",
            confidence=0.1,
            query_type="inventory",
            source_device_ids=[],
        ))

        result = await svc.query(
            db=mock_db,
            neo4j_client=None,
            question="which devices have telnet enabled?",
            org_id="00000000-0000-0000-0000-000000000001",
            top_k=5,
        )
        assert isinstance(result, NLIResponse)
        assert result.answer is not None
        assert 0.0 <= result.confidence <= 1.0
        assert result.graph_traversal_used is False
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
python -m pytest services/api/tests/api/test_nli_unit.py::TestNLIService -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.nli.nli_service'`

- [ ] **Step 3: Create nli_service.py**

Create `services/api/app/services/nli/nli_service.py`:

```python
"""
NLI Service Orchestrator

Coordinates the five-stage RAG pipeline:
  1. IntentClassifier  — determine domains + graph flag
  2. VectorRetriever   — pgvector cosine search
  3. GraphTraverser    — Neo4j topology context (optional)
  4. ContextBuilder    — assemble prompt text
  5. ClaudeSynthesizer — generate and parse answer
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import NLIQuery, NLIResponse, NLISource
from app.services.nli.intent_classifier import IntentClassifier
from app.services.nli.vector_retriever import VectorRetriever
from app.services.nli.graph_traverser import GraphTraverser
from app.services.nli.context_builder import ContextBuilder
from app.services.nli.claude_synthesizer import ClaudeSynthesizer

logger = logging.getLogger(__name__)


class NLIService:
    """Orchestrates the five-stage NLI/RAG pipeline."""

    def __init__(self, api_key: str, model: str) -> None:
        self._classifier = IntentClassifier()
        self._retriever = VectorRetriever()
        self._traverser = GraphTraverser()
        self._builder = ContextBuilder()
        self._synthesizer = ClaudeSynthesizer(api_key=api_key, model=model)
        self.available = self._synthesizer.available

    async def query(
        self,
        db: AsyncSession,
        neo4j_client,
        question: str,
        org_id: str,
        top_k: int = 5,
    ) -> NLIResponse:
        # Stage 1 — intent classification
        intent = self._classifier.classify(question)
        logger.info(
            "NLI query: domains=%s needs_graph=%s",
            intent.domains,
            intent.needs_graph,
        )

        # Stage 2 — vector retrieval (parallel across domains)
        retrieval_tasks = [
            self._retriever.retrieve(
                db=db,
                org_id=org_id,
                domain=domain,
                query_vec=self._classifier._centroids[domain],  # reuse centroid as proxy
                top_k=top_k,
            )
            for domain in intent.domains
        ]
        # Use the actual question embedding for retrieval
        from app.services.nli.intent_classifier import _get_model
        import numpy as np
        q_vec = _get_model().encode(question, convert_to_numpy=True)

        retrieval_tasks = [
            self._retriever.retrieve(
                db=db,
                org_id=org_id,
                domain=domain,
                query_vec=q_vec,
                top_k=top_k,
            )
            for domain in intent.domains
        ]
        domain_results = await asyncio.gather(*retrieval_tasks)

        # Deduplicate by device_id, keeping highest similarity
        seen: dict[str, object] = {}
        for devices in domain_results:
            for d in devices:
                if d.device_id not in seen or d.similarity > seen[d.device_id].similarity:
                    seen[d.device_id] = d
        all_devices = sorted(seen.values(), key=lambda d: d.similarity, reverse=True)

        # Stage 3 — graph traversal (optional)
        graph_context = None
        graph_used = False
        if intent.needs_graph and neo4j_client is not None:
            graph_context = await self._traverser.traverse(
                neo4j_client=neo4j_client,
                question=question,
                anchor_devices=all_devices[:3],
                extracted_entities=intent.extracted_entities,
            )
            graph_used = graph_context is not None

        # Stage 4 — context assembly
        context_text, sources = self._builder.build(all_devices, graph_context)

        # Stage 5 — Claude synthesis
        synthesis = await self._synthesizer.synthesize(
            question=question,
            context=context_text,
        )

        return NLIResponse(
            answer=synthesis.answer,
            sources=sources,
            confidence=synthesis.confidence,
            query_type=synthesis.query_type,
            retrieved_device_count=len(all_devices),
            graph_traversal_used=graph_used,
        )
```

- [ ] **Step 4: Create the NLI route**

Create `services/api/app/api/routes/nli.py`:

```python
"""
NLI route — POST /query
Natural language query interface over pgvector + Neo4j + Claude.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import dependencies, schemas
from app.api.dependencies import get_current_user, get_db
from app.core.config import settings
from app.db.neo4j import get_neo4j_client

router = APIRouter()

# Module-level NLI service instance — loaded once on first request to avoid
# loading sentence-transformers at import time (adds ~3s to cold start for all tests)
_nli_service = None


def get_nli_service():
    global _nli_service
    if _nli_service is None:
        from app.services.nli.nli_service import NLIService
        _nli_service = NLIService(
            api_key=settings.ANTHROPIC_API_KEY,
            model=settings.ANTHROPIC_MODEL,
        )
    return _nli_service


@router.post("", response_model=schemas.NLIResponse)
async def natural_language_query(
    request: Request,
    query: schemas.NLIQuery,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(dependencies.get_db),
):
    """
    Answer a natural-language question about your network.

    The pipeline embeds the question, searches pgvector for relevant devices,
    optionally traverses Neo4j for topology context, then synthesises an answer
    via Claude. Returns the answer, source devices, and a confidence score.
    """
    if not query.question.strip():
        raise HTTPException(status_code=400, detail="Question must not be empty")

    nli = get_nli_service()

    if not nli.available:
        raise HTTPException(
            status_code=503,
            detail="NLI service not available: ANTHROPIC_API_KEY is not configured",
        )

    # Get Neo4j client (None if unavailable — pipeline degrades gracefully)
    try:
        neo4j_client = get_neo4j_client()
    except Exception:
        neo4j_client = None

    top_k = min(query.top_k, 20)

    try:
        result = await nli.query(
            db=db,
            neo4j_client=neo4j_client,
            question=query.question,
            org_id=str(current_user.organization_id),
            top_k=top_k,
        )
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Claude API request timed out")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"NLI pipeline error: {exc}")

    return result
```

- [ ] **Step 5: Wire nli.router into routes/__init__.py**

Open `services/api/app/api/routes/__init__.py` and add two lines:

```python
# Add to imports (after `from . import acl_snapshots, changes`):
from . import nli

# Add to router includes (after `router.include_router(changes.router, ...)`):
router.include_router(nli.router,   prefix="/query",   tags=["nli"])
```

The full file should now look like:

```python
"""
API routes package — aggregates all domain-specific routers.
"""
from fastapi import APIRouter
from . import health, portal, websocket
from . import discoveries, sites
from . import devices, agents, path_visualizer
from . import alerts, integrations
from . import acl_snapshots, changes
from . import nli

router = APIRouter()

router.include_router(health.router)
router.include_router(portal.router)
router.include_router(websocket.router,       tags=["websocket"])
router.include_router(discoveries.router,     prefix="/discoveries",   tags=["discoveries"])
router.include_router(sites.router,           prefix="/sites",         tags=["sites"])
router.include_router(devices.router,         prefix="/devices",       tags=["devices"])
router.include_router(agents.router,                                   tags=["agents"])
router.include_router(path_visualizer.router,                          tags=["path"])
router.include_router(alerts.router,                                   tags=["alerts"])
router.include_router(integrations.router,    prefix="/integrations",  tags=["integrations"])
router.include_router(acl_snapshots.router,   prefix="/acl-snapshots", tags=["acl-snapshots"])
router.include_router(changes.router,                                  tags=["changes"])
router.include_router(nli.router,             prefix="/query",         tags=["nli"])
```

- [ ] **Step 6: Run orchestrator unit tests**

```bash
python -m pytest services/api/tests/api/test_nli_unit.py::TestNLIService -v
```

Expected: all 3 tests pass.

- [ ] **Step 7: Run full suite**

```bash
make test
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add services/api/app/services/nli/nli_service.py \
        services/api/app/api/routes/nli.py \
        services/api/app/api/routes/__init__.py \
        services/api/tests/api/test_nli_unit.py
git commit -m "feat(nli): add NLIService orchestrator, POST /query route (Group 7 Task 7)"
```

---

## Task 8: Integration Tests

**Files:**
- Create: `services/api/tests/api/test_nli_integration.py`

Integration tests use the existing `client` and `async_client` fixtures from `conftest.py` (TestClient + dependency-overridden auth). Anthropic is mocked with a fixed fixture response. Real PostgreSQL and Neo4j connections are used where available; if they're not available in the test environment, tests use the mock DB from conftest.

- [ ] **Step 1: Create integration test file**

Create `services/api/tests/api/test_nli_integration.py`:

```python
"""
NLI integration tests.

Tests the full POST /api/v1/query pipeline with:
- Mocked Anthropic API (avoids real API cost and network dependency)
- Mocked sentence-transformers model (avoids 3s cold-start in CI)
- Real FastAPI routing, schema validation, auth middleware
- Mocked DB for device results (avoids needing populated vectors)
"""
import json
import pytest
import numpy as np
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient

# Fixed Anthropic response fixture
_CLAUDE_FIXTURE_TEXT = (
    "Three devices have Telnet enabled: access-sw-01, access-sw-02, and legacy-router-01. "
    "These are all in the branch site. Consider disabling Telnet and enabling SSH.\n"
    '{"confidence": 0.92, "query_type": "security", "source_device_ids": ["uuid-1", "uuid-2", "uuid-3"]}'
)


@pytest.fixture(autouse=True)
def mock_sentence_transformers():
    """Prevent sentence-transformers from loading the real model in tests."""
    mock_model = MagicMock()
    mock_model.encode.return_value = np.ones(768, dtype=np.float32)
    with patch("app.services.nli.intent_classifier.SentenceTransformer", return_value=mock_model):
        # Reset the module-level cached model so tests get the mock
        import app.services.nli.intent_classifier as clf_module
        clf_module._MODEL = None
        yield
        clf_module._MODEL = None


@pytest.fixture(autouse=True)
def mock_anthropic():
    """Mock Anthropic API to return the fixture response."""
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=_CLAUDE_FIXTURE_TEXT)]
    mock_client_instance = MagicMock()
    mock_client_instance.messages = MagicMock()
    mock_client_instance.messages.create = AsyncMock(return_value=mock_msg)
    with patch("app.services.nli.claude_synthesizer.AsyncAnthropic", return_value=mock_client_instance):
        # Reset cached NLI service so it picks up the mock
        import app.api.routes.nli as nli_route
        nli_route._nli_service = None
        yield
        nli_route._nli_service = None


@pytest.fixture
def mock_db_empty():
    """DB that returns no devices (simulates unpopulated vectors)."""
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    return mock_db


@pytest.fixture
def mock_db_with_devices():
    """DB that returns two mock devices."""
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [
        MagicMock(
            id="uuid-1",
            hostname="access-sw-01",
            vendor="Cisco",
            device_type="switch",
            metadata={"security_posture": {"telnet_enabled": True, "ssh_enabled": False}},
            compliance_scope=["PCI-BOUNDARY"],
            similarity=0.94,
        ),
        MagicMock(
            id="uuid-2",
            hostname="access-sw-02",
            vendor="Cisco",
            device_type="switch",
            metadata={"security_posture": {"telnet_enabled": True, "ssh_enabled": False}},
            compliance_scope=[],
            similarity=0.89,
        ),
    ]
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    return mock_db


class TestNLIRoute:
    def test_query_returns_200_and_valid_schema(self, client, mock_db_with_devices):
        """Full pipeline: security question → 200 with NLIResponse schema."""
        from app.api import dependencies
        from app.main import app

        app.dependency_overrides[dependencies.get_db] = lambda: mock_db_with_devices

        with patch("app.api.routes.nli.get_neo4j_client", return_value=None):
            with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}):
                response = client.post(
                    "/api/v1/query",
                    json={"question": "which devices have telnet enabled?"},
                )

        app.dependency_overrides.pop(dependencies.get_db, None)

        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert "sources" in data
        assert "confidence" in data
        assert "query_type" in data
        assert "retrieved_device_count" in data
        assert "graph_traversal_used" in data
        assert isinstance(data["confidence"], float)
        assert 0.0 <= data["confidence"] <= 1.0

    def test_query_empty_question_returns_400(self, client):
        response = client.post("/api/v1/query", json={"question": ""})
        assert response.status_code == 400

    def test_query_unauthenticated_returns_401(self, app):
        """Without mocked auth, endpoint returns 401."""
        with TestClient(app) as raw_client:
            response = raw_client.post(
                "/api/v1/query",
                json={"question": "show me all devices"},
            )
        assert response.status_code == 401

    def test_query_no_api_key_returns_503(self, client, mock_db_empty):
        """When ANTHROPIC_API_KEY is empty, endpoint returns 503."""
        from app.api import dependencies
        from app.main import app
        import app.api.routes.nli as nli_route

        app.dependency_overrides[dependencies.get_db] = lambda: mock_db_empty
        nli_route._nli_service = None  # force re-init with no key

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}), \
             patch("app.core.config.settings.ANTHROPIC_API_KEY", ""), \
             patch("app.api.routes.nli.get_neo4j_client", return_value=None):
            # Temporarily init service with no key
            from app.services.nli.nli_service import NLIService
            with patch("app.services.nli.intent_classifier.SentenceTransformer"):
                nli_route._nli_service = NLIService(api_key="", model="claude-sonnet-4-6")
            response = client.post(
                "/api/v1/query",
                json={"question": "show all devices"},
            )

        app.dependency_overrides.pop(dependencies.get_db, None)
        nli_route._nli_service = None  # cleanup
        assert response.status_code == 503

    def test_query_with_no_devices_returns_answer_with_no_context(self, client, mock_db_empty):
        """When vectors are not populated (Group 6a not yet run), answer gracefully states no data."""
        from app.api import dependencies
        from app.main import app

        app.dependency_overrides[dependencies.get_db] = lambda: mock_db_empty

        with patch("app.api.routes.nli.get_neo4j_client", return_value=None), \
             patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}):
            response = client.post(
                "/api/v1/query",
                json={"question": "which devices have telnet enabled?"},
            )

        app.dependency_overrides.pop(dependencies.get_db, None)
        assert response.status_code == 200
        data = response.json()
        assert data["retrieved_device_count"] == 0
        assert data["graph_traversal_used"] is False

    def test_query_topology_question_attempts_graph_traversal(self, client, mock_db_with_devices):
        """Topology questions set graph_traversal_used=True when Neo4j is available."""
        from app.api import dependencies
        from app.main import app
        from app.services.nli.graph_traverser import GraphContext, QueryShape

        app.dependency_overrides[dependencies.get_db] = lambda: mock_db_with_devices

        mock_neo4j = MagicMock()

        with patch("app.api.routes.nli.get_neo4j_client", return_value=mock_neo4j), \
             patch("app.services.nli.graph_traverser.GraphTraverser.traverse",
                   new_callable=lambda: lambda self, **kw: AsyncMock(
                       return_value=GraphContext(
                           nodes=[{"hostname": "access-sw-01"}],
                           edges=[],
                           query_shape=QueryShape.NEIGHBORHOOD,
                       )
                   )()), \
             patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}):
            response = client.post(
                "/api/v1/query",
                json={"question": "what connects to access-sw-01?"},
            )

        app.dependency_overrides.pop(dependencies.get_db, None)
        assert response.status_code == 200

    def test_top_k_clamped_to_20(self, client, mock_db_with_devices):
        """top_k > 20 is silently clamped."""
        from app.api import dependencies
        from app.main import app

        app.dependency_overrides[dependencies.get_db] = lambda: mock_db_with_devices

        with patch("app.api.routes.nli.get_neo4j_client", return_value=None), \
             patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}):
            response = client.post(
                "/api/v1/query",
                json={"question": "list all devices", "top_k": 999},
            )

        app.dependency_overrides.pop(dependencies.get_db, None)
        assert response.status_code == 200
```

- [ ] **Step 2: Run integration tests**

```bash
python -m pytest services/api/tests/api/test_nli_integration.py -v
```

Expected: all 7 tests pass.

- [ ] **Step 3: Run full suite**

```bash
make test
```

Expected: all tests pass (57 original + 28 new NLI tests).

- [ ] **Step 4: Commit**

```bash
git add services/api/tests/api/test_nli_integration.py
git commit -m "test(nli): add integration tests for POST /query pipeline (Group 7 Task 8)"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|-----------------|------|
| `POST /api/v1/query` endpoint | Task 7 |
| Intent classification (embedding + keywords) | Task 2 |
| pgvector cosine search per domain | Task 3 |
| `needs_graph` flag + Neo4j traversal | Tasks 2, 4 |
| Token-budgeted context assembly | Task 5 |
| Claude synthesis with confidence JSON | Task 6 |
| `NLIResponse` schema | Task 1 |
| `503` on missing API key | Tasks 6, 7, 8 |
| `400` on empty question | Tasks 7, 8 |
| Graceful degradation when no vectors | Tasks 3, 7, 8 |
| Graceful degradation when Neo4j down | Tasks 4, 7, 8 |
| `NLI_VECTOR_TOP_K` config | Task 1 |
| Rate limit (`10/minute`) | Not yet implemented — **add to Task 7** |

### Rate limiting omission fix

In `services/api/app/api/routes/nli.py`, add the rate limiter import and decorator (same pattern as `sites.py`). Add this to **Task 7, Step 4** after creating the route:

In the imports section of `nli.py`, add:
```python
from slowapi import Limiter
from slowapi.util import get_remote_address
limiter = Limiter(key_func=get_remote_address)
```

And decorate the route handler:
```python
@router.post("", response_model=schemas.NLIResponse)
@limiter.limit(settings.NLI_RATE_LIMIT)
async def natural_language_query(request: Request, ...):
```

**Type consistency check:** `QueryIntent.extracted_entities`, `GraphTraverser.traverse(extracted_entities=...)`, `NLIService.query` passes `intent.extracted_entities` — all consistent. `DeviceContext` used by both `VectorRetriever` and `GraphTraverser` — same import path `app.services.nli.vector_retriever`. `NLISource` imported from `app.api.schemas` in `context_builder.py` — consistent with Task 1.

**Docker note:** `sentence-transformers` downloads the `all-mpnet-base-v2` model (~420MB) from HuggingFace Hub on first use. In production Docker, add a volume mount for the model cache to avoid re-downloading on container restart:

```yaml
# In docker-compose.yml, under the api service:
volumes:
  - huggingface_cache:/root/.cache/huggingface
```

```yaml
# At the top-level volumes section:
volumes:
  huggingface_cache:
```

This is a docker-compose modification — add it as a manual step outside the automated tasks.
