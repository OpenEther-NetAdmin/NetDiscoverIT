# Group 9b Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build three new frontend pages (D3 topology map, compliance report viewer, NLI chat assistant) plus one backend topology endpoint, all wired together with tests.

**Architecture:** Feature-folder pattern under `src/pages/` matching `src/pages/changes/`. Backend: one new `GET /api/v1/topology` route pulling devices from PostgreSQL + device-to-device connections from Neo4j. Frontend: D3 v7 force simulation (isolated in `useEffect`), Chakra UI v2 tabs/forms/cards, `react-markdown` for NLI answer rendering.

**Tech Stack:** React 18, Chakra UI v2, React Router v6, D3 v7, react-markdown v8, Jest + RTL, FastAPI + SQLAlchemy async, existing `api.js` service class pattern.

---

## File Map

**Create (backend):**
- `services/api/app/api/routes/topology.py` — GET /topology route
- `tests/api/test_topology.py` — backend unit tests

**Modify (backend):**
- `services/api/app/api/schemas.py` — add TopologyNode, TopologyEdge, TopologyResponse
- `services/api/app/db/neo4j.py` — add `get_device_connections(org_id)` method
- `services/api/app/api/routes/__init__.py` — register topology router

**Modify (frontend infrastructure):**
- `services/frontend/src/services/api.js` — 5 new methods
- `services/frontend/src/App.js` — 3 new routes
- `services/frontend/src/components/Sidebar.jsx` — 3 new NavItems
- `services/frontend/package.json` — add d3, react-markdown

**Create (topology feature):**
- `services/frontend/src/pages/topology/topologyUtils.js`
- `services/frontend/src/pages/topology/useTopology.js`
- `services/frontend/src/pages/topology/TopologyMap.jsx`
- `services/frontend/src/__tests__/TopologyMap.test.jsx`

**Create (compliance feature):**
- `services/frontend/src/pages/compliance/complianceUtils.js`
- `services/frontend/src/pages/compliance/useReportPolling.js`
- `services/frontend/src/pages/compliance/GenerateTab.jsx`
- `services/frontend/src/pages/compliance/HistoryTab.jsx`
- `services/frontend/src/pages/compliance/ComplianceViewer.jsx`
- `services/frontend/src/__tests__/ComplianceViewer.test.jsx`

**Create (assistant feature):**
- `services/frontend/src/pages/assistant/assistantUtils.js`
- `services/frontend/src/pages/assistant/SourceCard.jsx`
- `services/frontend/src/pages/assistant/ChatMessage.jsx`
- `services/frontend/src/pages/assistant/AssistantPage.jsx`
- `services/frontend/src/__tests__/AssistantPage.test.jsx`

**Create (integration):**
- `services/frontend/src/__tests__/integration/TopologyCompliance.test.jsx`

---

### Task 1: Add topology schemas to schemas.py and `get_device_connections` to neo4j.py

**Files:**
- Modify: `services/api/app/api/schemas.py` (append after `ComplianceReportListResponse`)
- Modify: `services/api/app/db/neo4j.py` (add method to `Neo4jClient`)

- [ ] **Step 1: Append topology schemas to `services/api/app/api/schemas.py`**

Add this block at the end of the file, after `ComplianceReportListResponse`:

```python
# ---------------------------------------------------------------------------
# Topology schemas
# ---------------------------------------------------------------------------

class TopologyNode(BaseModel):
    id: str
    type: str = "device"
    hostname: str
    device_type: str  # router | switch | firewall | server | unknown
    management_ip: str | None = None
    compliance_scope: list[str] = []
    organization_id: str


class TopologyEdge(BaseModel):
    source: str  # device UUID
    target: str  # device UUID


class TopologyResponse(BaseModel):
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]
    node_count: int
    edge_count: int
```

- [ ] **Step 2: Add `get_device_connections` to `Neo4jClient` in `services/api/app/db/neo4j.py`**

Find the `get_topology` method (line ~325) and add this method directly after it:

```python
    async def get_device_connections(self, organization_id: str) -> list[dict]:
        """Return device-to-device connections for an org as {source, target} dicts.

        Collapses interface-level CONNECTED_TO edges to device-level pairs.
        Deduplicates by requiring d1.id < d2.id so each pair appears once.
        Returns an empty list if the driver is not connected.
        """
        if not self._driver:
            return []

        cypher = (
            "MATCH (d1:Device {organization_id: $org_id})"
            "-[:HAS_INTERFACE]->(:Interface)-[:CONNECTED_TO]->"
            "(:Interface)<-[:HAS_INTERFACE]-(d2:Device) "
            "WHERE d2.organization_id = $org_id AND d1.id < d2.id "
            "RETURN DISTINCT d1.id AS source, d2.id AS target"
        )
        edges = []
        async with self._driver.session() as session:
            result = await session.run(cypher, {"org_id": organization_id})
            async for record in result:
                edges.append(
                    {"source": str(record["source"]), "target": str(record["target"])}
                )
        return edges
```

- [ ] **Step 3: Verify schemas import cleanly**

```bash
cd /home/openether/NetDiscoverIT/services/api
python -c "from app.api.schemas import TopologyResponse; print('OK')"
```
Expected: `OK`

---

### Task 2: Create the topology route and register it

**Files:**
- Create: `services/api/app/api/routes/topology.py`
- Modify: `services/api/app/api/routes/__init__.py`

- [ ] **Step 1: Create `services/api/app/api/routes/topology.py`**

```python
"""
Topology route — GET /api/v1/topology
Returns full network graph: device nodes from PostgreSQL + device-to-device
connections from Neo4j. Neo4j failure is handled gracefully (empty edges).
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import schemas
from app.api.dependencies import get_current_user, get_db
from app.db.neo4j import get_neo4j_client
from app.models.models import Device

router = APIRouter()


def _device_type(role: str | None) -> str:
    """Map device_role string to one of router|switch|firewall|server|unknown."""
    r = (role or "").lower()
    if "router" in r:
        return "router"
    if "switch" in r:
        return "switch"
    if "firewall" in r or r == "fw":
        return "firewall"
    if "server" in r:
        return "server"
    return "unknown"


@router.get("", response_model=schemas.TopologyResponse)
async def get_topology(
    current_user: schemas.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all devices for this org with their topology connections.

    Devices come from PostgreSQL (has compliance_scope, device_role, etc.).
    Edges come from Neo4j. If Neo4j is unavailable, nodes are still returned
    with an empty edges list.
    """
    org_uuid = UUID(current_user.organization_id)

    result = await db.execute(
        select(Device).where(Device.organization_id == org_uuid)
    )
    devices = result.scalars().all()

    nodes = [
        schemas.TopologyNode(
            id=str(d.id),
            type="device",
            hostname=d.hostname or str(d.id)[:8],
            device_type=_device_type(d.device_role),
            management_ip=str(d.ip_address) if d.ip_address else None,
            compliance_scope=list(d.compliance_scope or []),
            organization_id=str(d.organization_id),
        )
        for d in devices
    ]

    edges: list[schemas.TopologyEdge] = []
    try:
        neo4j = get_neo4j_client()
        raw = await neo4j.get_device_connections(current_user.organization_id)
        edges = [
            schemas.TopologyEdge(source=e["source"], target=e["target"])
            for e in raw
        ]
    except Exception:
        # Neo4j unavailable — return nodes with no edges
        pass

    return schemas.TopologyResponse(
        nodes=nodes,
        edges=edges,
        node_count=len(nodes),
        edge_count=len(edges),
    )
```

- [ ] **Step 2: Register the router in `services/api/app/api/routes/__init__.py`**

Add the import and `include_router` call alongside the existing ones:

```python
from . import topology   # add this import line with the others
```

And add this line after the `compliance_reports` include_router:

```python
router.include_router(topology.router, prefix="/topology", tags=["topology"])
```

- [ ] **Step 3: Verify the route appears in OpenAPI docs**

```bash
cd /home/openether/NetDiscoverIT
python -c "
from services.api.app.main import app
routes = [r.path for r in app.routes]
print([r for r in routes if 'topology' in r])
"
```
Expected: `['/api/v1/topology']`

---

### Task 3: Backend topology tests

**Files:**
- Create: `tests/api/test_topology.py`

- [ ] **Step 1: Create `tests/api/test_topology.py`**

```python
"""Tests for GET /api/v1/topology"""
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_db
from app.api.schemas import User
from app.main import app

client = TestClient(app)

ORG_ID = str(uuid4())
USER_ID = str(uuid4())
MOCK_USER = User(
    id=USER_ID,
    email="test@example.com",
    organization_id=ORG_ID,
    role="engineer",
    is_active=True,
)


def _make_device(device_id=None, hostname="RTR-1", role="core_router",
                 ip="10.0.0.1", scope=None):
    d = MagicMock()
    d.id = device_id or uuid4()
    d.hostname = hostname
    d.device_role = role
    d.ip_address = ip
    d.compliance_scope = scope or []
    d.organization_id = ORG_ID
    return d


def _db_override(devices):
    """Return a FastAPI dependency override that yields a mock AsyncSession."""
    async def override():
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = devices
        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)
        yield session
    return override


def test_topology_unauthenticated():
    resp = client.get("/api/v1/topology")
    assert resp.status_code == 401


def test_topology_returns_nodes(monkeypatch):
    dev1 = _make_device(hostname="RTR-CORE-1", role="core_router",
                        scope=["PCI-CDE"])
    dev2 = _make_device(hostname="SW-ACCESS-1", role="access_switch")

    mock_neo4j = MagicMock()
    mock_neo4j.get_device_connections = AsyncMock(return_value=[
        {"source": str(dev1.id), "target": str(dev2.id)}
    ])
    monkeypatch.setattr("app.api.routes.topology.get_neo4j_client",
                        lambda: mock_neo4j)

    app.dependency_overrides[get_current_user] = lambda: MOCK_USER
    app.dependency_overrides[get_db] = _db_override([dev1, dev2])
    try:
        resp = client.get("/api/v1/topology")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["node_count"] == 2
    assert data["edge_count"] == 1
    hostnames = [n["hostname"] for n in data["nodes"]]
    assert "RTR-CORE-1" in hostnames
    assert data["nodes"][0]["compliance_scope"] == ["PCI-CDE"] or \
           data["nodes"][1]["compliance_scope"] == ["PCI-CDE"]


def test_topology_device_type_mapping(monkeypatch):
    devices = [
        _make_device(hostname="R1", role="core_router"),
        _make_device(hostname="SW1", role="distribution_switch"),
        _make_device(hostname="FW1", role="edge_firewall"),
        _make_device(hostname="SRV1", role="app_server"),
        _make_device(hostname="X1", role=None),
    ]

    mock_neo4j = MagicMock()
    mock_neo4j.get_device_connections = AsyncMock(return_value=[])
    monkeypatch.setattr("app.api.routes.topology.get_neo4j_client",
                        lambda: mock_neo4j)

    app.dependency_overrides[get_current_user] = lambda: MOCK_USER
    app.dependency_overrides[get_db] = _db_override(devices)
    try:
        resp = client.get("/api/v1/topology")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    type_map = {n["hostname"]: n["device_type"] for n in resp.json()["nodes"]}
    assert type_map["R1"] == "router"
    assert type_map["SW1"] == "switch"
    assert type_map["FW1"] == "firewall"
    assert type_map["SRV1"] == "server"
    assert type_map["X1"] == "unknown"


def test_topology_neo4j_failure_returns_nodes_no_edges(monkeypatch):
    dev1 = _make_device()

    monkeypatch.setattr("app.api.routes.topology.get_neo4j_client",
                        lambda: (_ for _ in ()).throw(RuntimeError("Neo4j down")))

    app.dependency_overrides[get_current_user] = lambda: MOCK_USER
    app.dependency_overrides[get_db] = _db_override([dev1])
    try:
        resp = client.get("/api/v1/topology")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["node_count"] == 1
    assert data["edge_count"] == 0
    assert data["edges"] == []
```

- [ ] **Step 2: Run the backend topology tests**

```bash
cd /home/openether/NetDiscoverIT
make test 2>&1 | grep -E "test_topology|PASSED|FAILED|ERROR"
```
Expected: all 4 topology tests PASSED

- [ ] **Step 3: Commit**

```bash
git add services/api/app/api/schemas.py \
        services/api/app/db/neo4j.py \
        services/api/app/api/routes/topology.py \
        services/api/app/api/routes/__init__.py \
        tests/api/test_topology.py
git commit -m "feat(topology): add GET /api/v1/topology endpoint with device nodes + Neo4j connections"
```

---

### Task 4: Install npm dependencies and extend api.js

**Files:**
- Modify: `services/frontend/package.json` (via npm install)
- Modify: `services/frontend/src/services/api.js`

- [ ] **Step 1: Install d3 and react-markdown**

```bash
cd /home/openether/NetDiscoverIT/services/frontend
npm install d3 react-markdown
```
Expected: both packages appear in `package.json` dependencies. No peer dependency errors.

- [ ] **Step 2: Add 5 new methods to `services/frontend/src/services/api.js`**

Add these methods inside the `ApiService` class, after `getMspOverview()`:

```js
  getTopology() {
    return this.request('/api/v1/topology');
  }

  createComplianceReport({ framework, format, period_start, period_end, scope_override = null }) {
    return this.request('/api/v1/compliance/reports', {
      method: 'POST',
      body: JSON.stringify({ framework, format, period_start, period_end, scope_override }),
    });
  }

  getComplianceReport(id) {
    return this.request(`/api/v1/compliance/reports/${id}`);
  }

  listComplianceReports({ status, framework, skip = 0, limit = 20 } = {}) {
    const params = new URLSearchParams();
    if (status) params.set('status', status);
    if (framework) params.set('framework', framework);
    params.set('skip', skip);
    params.set('limit', limit);
    return this.request(`/api/v1/compliance/reports?${params.toString()}`);
  }

  queryAssistant({ question, top_k = 5 }) {
    return this.request('/api/v1/query', {
      method: 'POST',
      body: JSON.stringify({ question, top_k }),
    });
  }
```

- [ ] **Step 3: Add api.js tests for the 5 new methods in `services/frontend/src/__tests__/api.test.js`**

Open the existing `api.test.js` and append these tests (the file already mocks `fetch`):

```js
describe('getTopology', () => {
  test('calls GET /api/v1/topology', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true, status: 200,
      json: async () => ({ nodes: [], edges: [], node_count: 0, edge_count: 0 }),
    });
    const result = await api.getTopology();
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/topology'),
      expect.objectContaining({ headers: expect.any(Object) })
    );
    expect(result.node_count).toBe(0);
  });
});

describe('createComplianceReport', () => {
  test('calls POST /api/v1/compliance/reports', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true, status: 202,
      json: async () => ({ id: 'rpt-1', status: 'pending', framework: 'pci_dss', format: 'pdf' }),
    });
    const result = await api.createComplianceReport({
      framework: 'pci_dss', format: 'pdf',
      period_start: '2025-01-01', period_end: '2025-12-31',
    });
    expect(result.status).toBe('pending');
    const [url, opts] = fetch.mock.calls[0];
    expect(url).toContain('/api/v1/compliance/reports');
    expect(JSON.parse(opts.body).framework).toBe('pci_dss');
  });
});

describe('listComplianceReports', () => {
  test('builds query string correctly', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true, status: 200,
      json: async () => ({ items: [], total: 0, skip: 0, limit: 20 }),
    });
    await api.listComplianceReports({ status: 'completed', framework: 'hipaa' });
    const [url] = fetch.mock.calls[0];
    expect(url).toContain('status=completed');
    expect(url).toContain('framework=hipaa');
  });
});

describe('queryAssistant', () => {
  test('calls POST /api/v1/query with question', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true, status: 200,
      json: async () => ({
        answer: 'Two routers.', sources: [], confidence: 0.9,
        query_type: 'inventory', retrieved_device_count: 2, graph_traversal_used: false,
      }),
    });
    const result = await api.queryAssistant({ question: 'How many routers?' });
    expect(result.confidence).toBe(0.9);
    const [url, opts] = fetch.mock.calls[0];
    expect(url).toContain('/api/v1/query');
    expect(JSON.parse(opts.body).question).toBe('How many routers?');
    expect(JSON.parse(opts.body).top_k).toBe(5);
  });
});
```

- [ ] **Step 4: Run api tests**

```bash
cd /home/openether/NetDiscoverIT/services/frontend
npm test -- --watchAll=false --testPathPattern="api.test"
```
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add services/frontend/package.json services/frontend/package-lock.json \
        services/frontend/src/services/api.js \
        services/frontend/src/__tests__/api.test.js
git commit -m "feat(frontend): install d3+react-markdown, add 5 api.js methods for topology/compliance/assistant"
```

---

### Task 5: App.js routes and Sidebar nav items

**Files:**
- Modify: `services/frontend/src/App.js`
- Modify: `services/frontend/src/components/Sidebar.jsx`

- [ ] **Step 1: Add 3 new routes to `services/frontend/src/App.js`**

Current `App.js` has these imports at the top — add three more:
```js
import TopologyMap from './pages/topology/TopologyMap';
import ComplianceViewer from './pages/compliance/ComplianceViewer';
import AssistantPage from './pages/assistant/AssistantPage';
```

Inside the `<Routes>` block, add after the `/changes/:id` route:
```jsx
<Route path="/topology"    element={<TopologyMap />} />
<Route path="/compliance"  element={<ComplianceViewer />} />
<Route path="/assistant"   element={<AssistantPage />} />
```

- [ ] **Step 2: Add 3 new NavItems to `services/frontend/src/components/Sidebar.jsx`**

Add 3 icon imports to the existing `react-icons/fi` import line:
```js
import { FiGrid, FiServer, FiSearch, FiMap, FiSettings, FiClipboard,
         FiGlobe, FiShield, FiMessageSquare } from 'react-icons/fi';
```

In the `<VStack>` block, add after `<NavItem to="/changes" ...>Changes</NavItem>`:
```jsx
<NavItem to="/topology"   icon={FiGlobe}>Network Map</NavItem>
<NavItem to="/compliance" icon={FiShield}>Compliance</NavItem>
<NavItem to="/assistant"  icon={FiMessageSquare}>Assistant</NavItem>
```

- [ ] **Step 3: Create placeholder stubs for the three pages (so App.js compiles)**

```bash
mkdir -p /home/openether/NetDiscoverIT/services/frontend/src/pages/topology
mkdir -p /home/openether/NetDiscoverIT/services/frontend/src/pages/compliance
mkdir -p /home/openether/NetDiscoverIT/services/frontend/src/pages/assistant
```

Create stub `services/frontend/src/pages/topology/TopologyMap.jsx`:
```jsx
import React from 'react';
import { Box, Text } from '@chakra-ui/react';
const TopologyMap = () => <Box p={6}><Text>Topology Map — coming soon</Text></Box>;
export default TopologyMap;
```

Create stub `services/frontend/src/pages/compliance/ComplianceViewer.jsx`:
```jsx
import React from 'react';
import { Box, Text } from '@chakra-ui/react';
const ComplianceViewer = () => <Box p={6}><Text>Compliance — coming soon</Text></Box>;
export default ComplianceViewer;
```

Create stub `services/frontend/src/pages/assistant/AssistantPage.jsx`:
```jsx
import React from 'react';
import { Box, Text } from '@chakra-ui/react';
const AssistantPage = () => <Box p={6}><Text>Assistant — coming soon</Text></Box>;
export default AssistantPage;
```

- [ ] **Step 4: Verify the frontend compiles**

```bash
cd /home/openether/NetDiscoverIT/services/frontend
npm run build 2>&1 | tail -10
```
Expected: `Successfully compiled.` (or similar)

- [ ] **Step 5: Commit**

```bash
git add services/frontend/src/App.js \
        services/frontend/src/components/Sidebar.jsx \
        services/frontend/src/pages/topology/TopologyMap.jsx \
        services/frontend/src/pages/compliance/ComplianceViewer.jsx \
        services/frontend/src/pages/assistant/AssistantPage.jsx
git commit -m "feat(frontend): add topology/compliance/assistant routes and sidebar nav items"
```

---

### Task 6: topologyUtils.js

**Files:**
- Create: `services/frontend/src/pages/topology/topologyUtils.js`

- [ ] **Step 1: Create `services/frontend/src/pages/topology/topologyUtils.js`**

```js
// Node shape/color config by device type
export const NODE_STYLES = {
  router:   { shape: 'circle',  fill: '#3182CE', r: 18 },
  switch:   { shape: 'rect',    fill: '#718096', size: 32 },
  firewall: { shape: 'diamond', fill: '#E53E3E', size: 24 },
  server:   { shape: 'wideRect', fill: '#38A169', w: 36, h: 20 },
  unknown:  { shape: 'circle',  fill: '#A0AEC0', r: 16 },
};

export function getNodeStyle(deviceType) {
  return NODE_STYLES[deviceType] || NODE_STYLES.unknown;
}

// Compliance scope → badge dot color (first matching scope wins)
const SCOPE_BADGE_RULES = [
  { tags: ['PCI-CDE', 'PCI-BOUNDARY'],       color: '#DD6B20' },
  { tags: ['HIPAA-PHI'],                      color: '#6B46C1' },
  { tags: ['SOX-FINANCIAL'],                  color: '#D69E2E' },
  { tags: ['FEDRAMP-BOUNDARY'],               color: '#C53030' },
  { tags: ['ISO27001', 'SOC2', 'NIST-CSF'],  color: '#2B6CB0' },
];

export function getBadgeColor(complianceScope = []) {
  if (!complianceScope.length) return null;
  for (const { tags, color } of SCOPE_BADGE_RULES) {
    if (complianceScope.some((s) => tags.includes(s))) return color;
  }
  return null;
}

export function truncate(str, maxLen) {
  if (!str) return '';
  return str.length > maxLen ? `${str.slice(0, maxLen)}…` : str;
}

export const COMPLIANCE_SCOPE_OPTIONS = [
  'PCI-CDE', 'PCI-BOUNDARY', 'HIPAA-PHI', 'SOX-FINANCIAL',
  'FEDRAMP-BOUNDARY', 'ISO27001', 'SOC2', 'NIST-CSF',
];
```

- [ ] **Step 2: Verify exports compile (no syntax errors)**

```bash
cd /home/openether/NetDiscoverIT/services/frontend
node -e "const u = require('./src/pages/topology/topologyUtils.js'); console.log(Object.keys(u))"
```
Expected: `[ 'NODE_STYLES', 'getNodeStyle', 'SCOPE_BADGE_RULES' ... ]` (all exports listed)

If the above fails because CRA uses ESM, run the build check instead:
```bash
npm run build 2>&1 | grep -E "ERROR|compiled"
```

---

### Task 7: useTopology.js hook

**Files:**
- Create: `services/frontend/src/pages/topology/useTopology.js`

- [ ] **Step 1: Create `services/frontend/src/pages/topology/useTopology.js`**

```js
import { useState, useEffect, useMemo } from 'react';
import api from '../../services/api';

/**
 * Fetches full topology from GET /api/v1/topology and provides filtered
 * node/edge arrays for the D3 canvas.
 *
 * Returns:
 *   nodes, edges   — filtered arrays (pass directly into D3 effect)
 *   loading        — true while fetch in-flight
 *   error          — error message string or null
 *   reload         — call to re-fetch
 *   setHostnameFilter — (string) → filter nodes by hostname substring
 *   setScopeFilter    — (string) → filter nodes by compliance scope tag
 */
export function useTopology() {
  const [rawNodes, setRawNodes] = useState([]);
  const [rawEdges, setRawEdges] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [hostnameFilter, setHostnameFilter] = useState('');
  const [scopeFilter, setScopeFilter] = useState('');

  const reload = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getTopology();
      setRawNodes(data.nodes || []);
      setRawEdges(data.edges || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    reload();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const { nodes, edges } = useMemo(() => {
    let filtered = rawNodes;

    if (hostnameFilter) {
      const lower = hostnameFilter.toLowerCase();
      filtered = filtered.filter(
        (n) => n.hostname?.toLowerCase().includes(lower)
      );
    }

    if (scopeFilter) {
      filtered = filtered.filter(
        (n) => Array.isArray(n.compliance_scope) && n.compliance_scope.includes(scopeFilter)
      );
    }

    const filteredIds = new Set(filtered.map((n) => n.id));
    const filteredEdges = rawEdges.filter(
      (e) => filteredIds.has(e.source) && filteredIds.has(e.target)
    );

    return { nodes: filtered, edges: filteredEdges };
  }, [rawNodes, rawEdges, hostnameFilter, scopeFilter]);

  return { nodes, edges, loading, error, reload, setHostnameFilter, setScopeFilter };
}
```

---

### Task 8: TopologyMap.jsx (D3 canvas + filter bar + popover)

**Files:**
- Modify: `services/frontend/src/pages/topology/TopologyMap.jsx` (replace the stub)

- [ ] **Step 1: Replace stub with full `TopologyMap.jsx`**

```jsx
import React, { useEffect, useRef, useState } from 'react';
import * as d3 from 'd3';
import {
  Box, Flex, Heading, Input, InputGroup, InputLeftElement,
  Select, Button, Spinner, Text,
  Popover, PopoverTrigger, PopoverContent, PopoverBody,
  Badge, Tag, TagLabel, Wrap, WrapItem,
} from '@chakra-ui/react';
import { FiSearch, FiRefreshCw } from 'react-icons/fi';
import { useTopology } from './useTopology';
import {
  getNodeStyle, getBadgeColor, truncate, COMPLIANCE_SCOPE_OPTIONS,
} from './topologyUtils';

const LEGEND_TYPES = [
  { label: 'Router',   color: '#3182CE', shape: 'circle' },
  { label: 'Switch',   color: '#718096', shape: 'square' },
  { label: 'Firewall', color: '#E53E3E', shape: 'diamond' },
  { label: 'Server',   color: '#38A169', shape: 'square' },
  { label: 'Unknown',  color: '#A0AEC0', shape: 'circle' },
];

const LEGEND_SCOPES = [
  { label: 'PCI',      color: '#DD6B20' },
  { label: 'HIPAA',    color: '#6B46C1' },
  { label: 'SOX',      color: '#D69E2E' },
  { label: 'FedRAMP',  color: '#C53030' },
  { label: 'Other',    color: '#2B6CB0' },
];

const TopologyMap = () => {
  const { nodes, edges, loading, error, reload, setHostnameFilter, setScopeFilter } =
    useTopology();
  const svgRef = useRef(null);
  const [selectedNode, setSelectedNode] = useState(null);
  const [popoverPos, setPopoverPos] = useState({ x: 0, y: 0 });
  const [searchValue, setSearchValue] = useState('');
  const [scopeValue, setScopeValue] = useState('');

  const handleSearchChange = (e) => {
    setSearchValue(e.target.value);
    setHostnameFilter(e.target.value);
  };

  const handleScopeChange = (e) => {
    setScopeValue(e.target.value);
    setScopeFilter(e.target.value);
  };

  // D3 effect — runs when filtered data changes
  useEffect(() => {
    if (!svgRef.current || loading || error) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const width = svgRef.current.clientWidth || 800;
    const height = svgRef.current.clientHeight || 600;

    const g = svg.append('g');
    svg.call(
      d3.zoom().scaleExtent([0.2, 4]).on('zoom', (event) => {
        g.attr('transform', event.transform);
      })
    );

    if (!nodes.length) return;

    // Clone data — D3 mutates objects during simulation
    const simNodes = nodes.map((n) => ({ ...n }));
    const nodeById = Object.fromEntries(simNodes.map((n) => [n.id, n]));
    const simEdges = edges
      .filter((e) => nodeById[e.source] && nodeById[e.target])
      .map((e) => ({ source: nodeById[e.source], target: nodeById[e.target] }));

    const simulation = d3
      .forceSimulation(simNodes)
      .force('link', d3.forceLink(simEdges).id((d) => d.id).distance(90))
      .force('charge', d3.forceManyBody().strength(-250))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide(30));

    const link = g
      .append('g')
      .attr('stroke', '#CBD5E0')
      .attr('stroke-width', 1.5)
      .selectAll('line')
      .data(simEdges)
      .join('line');

    const node = g
      .append('g')
      .selectAll('g')
      .data(simNodes)
      .join('g')
      .attr('cursor', 'pointer')
      .call(
        d3
          .drag()
          .on('start', (event, d) => {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
          })
          .on('drag', (event, d) => {
            d.fx = event.x;
            d.fy = event.y;
          })
          .on('end', (event, d) => {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
          })
      )
      .on('click', (event, d) => {
        event.stopPropagation();
        if (!svgRef.current) return;
        const rect = svgRef.current.getBoundingClientRect();
        setPopoverPos({
          x: event.clientX - rect.left,
          y: event.clientY - rect.top,
        });
        setSelectedNode(d);
      });

    // Draw shape based on device_type
    node.each(function drawShape(d) {
      const el = d3.select(this);
      const style = getNodeStyle(d.device_type);
      if (style.shape === 'circle') {
        el.append('circle')
          .attr('r', style.r)
          .attr('fill', style.fill)
          .attr('stroke', 'white')
          .attr('stroke-width', 2);
      } else if (style.shape === 'rect' || style.shape === 'wideRect') {
        const w = style.w || style.size;
        const h = style.h || style.size;
        el.append('rect')
          .attr('x', -w / 2)
          .attr('y', -h / 2)
          .attr('width', w)
          .attr('height', h)
          .attr('rx', 3)
          .attr('fill', style.fill)
          .attr('stroke', 'white')
          .attr('stroke-width', 2);
      } else if (style.shape === 'diamond') {
        el.append('rect')
          .attr('x', -style.size / 2)
          .attr('y', -style.size / 2)
          .attr('width', style.size)
          .attr('height', style.size)
          .attr('fill', style.fill)
          .attr('stroke', 'white')
          .attr('stroke-width', 2)
          .attr('transform', 'rotate(45)');
      }
    });

    // Compliance scope badge dot
    node.each(function drawBadge(d) {
      const badgeColor = getBadgeColor(d.compliance_scope);
      if (badgeColor) {
        d3.select(this)
          .append('circle')
          .attr('cx', 14)
          .attr('cy', -14)
          .attr('r', 6)
          .attr('fill', badgeColor)
          .attr('stroke', 'white')
          .attr('stroke-width', 1.5);
      }
    });

    // Hostname label
    node
      .append('text')
      .attr('y', 28)
      .attr('text-anchor', 'middle')
      .attr('font-size', '10px')
      .attr('fill', '#4A5568')
      .attr('pointer-events', 'none')
      .text((d) => truncate(d.hostname, 12));

    simulation.on('tick', () => {
      link
        .attr('x1', (d) => d.source.x)
        .attr('y1', (d) => d.source.y)
        .attr('x2', (d) => d.target.x)
        .attr('y2', (d) => d.target.y);
      node.attr('transform', (d) => `translate(${d.x},${d.y})`);
    });

    svg.on('click', () => setSelectedNode(null));

    return () => {
      simulation.stop();
    };
  }, [nodes, edges, loading, error]);

  return (
    <Box p={6} h="100%" display="flex" flexDirection="column">
      <Flex justify="space-between" align="center" mb={4}>
        <Heading size="lg">Network Map</Heading>
        <Button leftIcon={<FiRefreshCw />} size="sm" onClick={reload}>
          Refresh
        </Button>
      </Flex>

      {/* Filter bar */}
      <Flex gap={3} mb={4} flexWrap="wrap">
        <InputGroup maxW="240px">
          <InputLeftElement pointerEvents="none">
            <FiSearch color="gray" />
          </InputLeftElement>
          <Input
            placeholder="Search by hostname"
            value={searchValue}
            onChange={handleSearchChange}
          />
        </InputGroup>
        <Select
          aria-label="Filter by compliance scope"
          maxW="200px"
          value={scopeValue}
          onChange={handleScopeChange}
        >
          <option value="">All scopes</option>
          {COMPLIANCE_SCOPE_OPTIONS.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </Select>
      </Flex>

      {/* Canvas */}
      <Box flex="1" position="relative" bg="white" borderRadius="md"
           border="1px" borderColor="gray.200" overflow="hidden">
        {loading && (
          <Flex position="absolute" inset={0} align="center" justify="center" zIndex={1}>
            <Spinner size="xl" />
          </Flex>
        )}

        {error && !loading && (
          <Flex position="absolute" inset={0} align="center" justify="center"
                direction="column" gap={3} zIndex={1}>
            <Text color="red.500">{error}</Text>
            <Button size="sm" onClick={reload}>Retry</Button>
          </Flex>
        )}

        {!loading && !error && nodes.length === 0 && (
          <Flex position="absolute" inset={0} align="center" justify="center" zIndex={1}>
            <Text color="gray.500">
              No devices found. Run a discovery to populate your network map.
            </Text>
          </Flex>
        )}

        <svg
          ref={svgRef}
          width="100%"
          height="100%"
          data-testid="topology-svg"
        />

        {/* Node detail popover */}
        {selectedNode && (
          <Box
            position="absolute"
            left={`${popoverPos.x + 10}px`}
            top={`${popoverPos.y - 10}px`}
            bg="white"
            borderRadius="md"
            boxShadow="lg"
            border="1px"
            borderColor="gray.200"
            p={3}
            zIndex={10}
            minW="200px"
            maxW="260px"
          >
            <Text fontWeight="bold" mb={1}>{selectedNode.hostname}</Text>
            {selectedNode.management_ip && (
              <Text fontSize="sm" color="gray.600" mb={1}>{selectedNode.management_ip}</Text>
            )}
            <Badge colorScheme="blue" mb={2}>{selectedNode.device_type}</Badge>
            {selectedNode.compliance_scope?.length > 0 && (
              <Wrap mt={1}>
                {selectedNode.compliance_scope.map((s) => (
                  <WrapItem key={s}>
                    <Tag size="sm" colorScheme="orange"><TagLabel>{s}</TagLabel></Tag>
                  </WrapItem>
                ))}
              </Wrap>
            )}
          </Box>
        )}

        {/* Legend */}
        <Box
          position="absolute"
          bottom={3}
          left={3}
          bg="whiteAlpha.900"
          borderRadius="md"
          p={2}
          fontSize="10px"
          lineHeight="1.6"
          border="1px"
          borderColor="gray.100"
        >
          <Text fontWeight="bold" mb={1} color="gray.500">SHAPE = TYPE</Text>
          {LEGEND_TYPES.map(({ label, color }) => (
            <Flex key={label} align="center" gap={1} mb="1px">
              <Box w={3} h={3} borderRadius="50%" bg={color} flexShrink={0} />
              <Text color="gray.600">{label}</Text>
            </Flex>
          ))}
          <Text fontWeight="bold" mt={2} mb={1} color="gray.500">DOT = SCOPE</Text>
          {LEGEND_SCOPES.map(({ label, color }) => (
            <Flex key={label} align="center" gap={1} mb="1px">
              <Box w={2} h={2} borderRadius="50%" bg={color} flexShrink={0} />
              <Text color="gray.600">{label}</Text>
            </Flex>
          ))}
        </Box>
      </Box>
    </Box>
  );
};

export default TopologyMap;
```

---

### Task 9: TopologyMap tests

**Files:**
- Create: `services/frontend/src/__tests__/TopologyMap.test.jsx`

- [ ] **Step 1: Create `services/frontend/src/__tests__/TopologyMap.test.jsx`**

D3 is mocked so tests focus on the React layer (loading state, error state, filter bar, SVG presence). Testing D3 SVG internals in jsdom is unreliable and not needed.

```jsx
import React from 'react';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders, setAuthRole } from '../test-utils';
import TopologyMap from '../pages/topology/TopologyMap';
import api from '../services/api';

// Mock D3 — tests focus on the React layer, not D3 SVG rendering
jest.mock('d3', () => {
  const chain = () => {
    const obj = {};
    const methods = [
      'select','selectAll','remove','append','attr','on','call',
      'join','data','each','text','force','alphaTarget','restart',
      'stop','id','distance','strength','scaleExtent',
    ];
    methods.forEach((m) => { obj[m] = jest.fn(() => obj); });
    return obj;
  };
  return {
    select: jest.fn(() => chain()),
    forceSimulation: jest.fn(() => chain()),
    forceLink: jest.fn(() => chain()),
    forceManyBody: jest.fn(() => chain()),
    forceCenter: jest.fn(),
    forceCollide: jest.fn(),
    zoom: jest.fn(() => chain()),
    drag: jest.fn(() => chain()),
  };
});

jest.mock('../services/api', () => ({
  __esModule: true,
  default: {
    getTopology: jest.fn(),
    getMspOverview: jest.fn(),
    setActiveOrg: jest.fn(),
  },
}));

const MOCK_TOPOLOGY = {
  nodes: [
    { id: 'n1', type: 'device', hostname: 'RTR-CORE-1', device_type: 'router',
      management_ip: '10.0.0.1', compliance_scope: ['PCI-CDE'], organization_id: 'org-1' },
    { id: 'n2', type: 'device', hostname: 'SW-ACCESS-1', device_type: 'switch',
      management_ip: '10.0.0.2', compliance_scope: [], organization_id: 'org-1' },
  ],
  edges: [{ source: 'n1', target: 'n2' }],
  node_count: 2,
  edge_count: 1,
};

afterEach(() => { jest.clearAllMocks(); localStorage.clear(); });

test('shows spinner while loading', () => {
  api.getTopology.mockReturnValue(new Promise(() => {})); // never resolves
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('engineer');
  renderWithProviders(<TopologyMap />);
  expect(screen.getByRole('status')).toBeInTheDocument(); // Chakra Spinner has role="status"
});

test('renders SVG container after data loads', async () => {
  api.getTopology.mockResolvedValue(MOCK_TOPOLOGY);
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('engineer');
  renderWithProviders(<TopologyMap />);
  await waitFor(() =>
    expect(screen.getByTestId('topology-svg')).toBeInTheDocument()
  );
});

test('shows retry button on error', async () => {
  api.getTopology.mockRejectedValue(new Error('Network error'));
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('engineer');
  renderWithProviders(<TopologyMap />);
  const retryBtn = await screen.findByRole('button', { name: /retry/i });
  expect(retryBtn).toBeInTheDocument();
});

test('clicking Retry calls api.getTopology again', async () => {
  api.getTopology.mockRejectedValue(new Error('fail'));
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('engineer');
  renderWithProviders(<TopologyMap />);
  const retryBtn = await screen.findByRole('button', { name: /retry/i });
  await userEvent.click(retryBtn);
  expect(api.getTopology).toHaveBeenCalledTimes(2);
});

test('shows empty state when no devices returned', async () => {
  api.getTopology.mockResolvedValue({ nodes: [], edges: [], node_count: 0, edge_count: 0 });
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('engineer');
  renderWithProviders(<TopologyMap />);
  expect(await screen.findByText(/no devices found/i)).toBeInTheDocument();
});

test('filter bar inputs render', async () => {
  api.getTopology.mockResolvedValue(MOCK_TOPOLOGY);
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('engineer');
  renderWithProviders(<TopologyMap />);
  await waitFor(() => screen.getByTestId('topology-svg'));
  expect(screen.getByPlaceholderText(/search by hostname/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/filter by compliance scope/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run topology tests**

```bash
cd /home/openether/NetDiscoverIT/services/frontend
npm test -- --watchAll=false --testPathPattern="TopologyMap"
```
Expected: all 6 tests PASS

- [ ] **Step 3: Commit**

```bash
git add services/frontend/src/pages/topology/ \
        services/frontend/src/__tests__/TopologyMap.test.jsx
git commit -m "feat(topology): add TopologyMap page with D3 force simulation, filter bar, and tests"
```

---

### Task 10: complianceUtils.js

**Files:**
- Create: `services/frontend/src/pages/compliance/complianceUtils.js`

- [ ] **Step 1: Create `services/frontend/src/pages/compliance/complianceUtils.js`**

```js
export const FRAMEWORKS = [
  { id: 'pci_dss',   label: 'PCI-DSS v4.0', colorScheme: 'red' },
  { id: 'hipaa',     label: 'HIPAA',         colorScheme: 'purple' },
  { id: 'sox_itgc',  label: 'SOX ITGC',      colorScheme: 'yellow' },
  { id: 'iso_27001', label: 'ISO 27001',      colorScheme: 'blue' },
  { id: 'nist_csf',  label: 'NIST CSF',      colorScheme: 'cyan' },
  { id: 'fedramp',   label: 'FedRAMP',        colorScheme: 'green' },
  { id: 'soc2',      label: 'SOC 2',          colorScheme: 'teal' },
];

export const STATUS_COLORS = {
  pending:    'yellow',
  generating: 'yellow',
  completed:  'green',
  failed:     'red',
};

export const FORMAT_LABELS = {
  pdf:  'PDF',
  docx: 'DOCX',
  both: 'PDF + DOCX',
};

export function isTerminalStatus(status) {
  return status === 'completed' || status === 'failed';
}

/** Returns ISO date string for today minus `days` days. */
export function daysAgo(days) {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().split('T')[0];
}

/** Returns today's ISO date string. */
export function today() {
  return new Date().toISOString().split('T')[0];
}
```

---

### Task 11: useReportPolling.js

**Files:**
- Create: `services/frontend/src/pages/compliance/useReportPolling.js`

- [ ] **Step 1: Create `services/frontend/src/pages/compliance/useReportPolling.js`**

```js
import { useEffect, useRef } from 'react';
import api from '../../services/api';
import { isTerminalStatus } from './complianceUtils';

/**
 * Polls the compliance report list every 3 seconds while any report
 * in `reports` has a non-terminal status (pending or generating).
 *
 * When all reports reach terminal status the interval clears itself.
 * Also clears on unmount.
 *
 * @param {Array}    reports   - current reports array from HistoryTab state
 * @param {Function} onUpdate  - called with refreshed items[] on each tick
 */
export function useReportPolling(reports, onUpdate) {
  // Stable ref so the interval callback always sees the latest onUpdate
  const onUpdateRef = useRef(onUpdate);
  onUpdateRef.current = onUpdate;

  const hasPending = reports.some((r) => !isTerminalStatus(r.status));

  useEffect(() => {
    if (!hasPending) return;

    const interval = setInterval(async () => {
      try {
        const refreshed = await api.listComplianceReports();
        onUpdateRef.current(refreshed.items || []);
      } catch {
        // silent — will retry on next tick
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [hasPending]); // re-evaluate when hasPending changes (false→true or true→false)
}
```

---

### Task 12: GenerateTab.jsx

**Files:**
- Create: `services/frontend/src/pages/compliance/GenerateTab.jsx`

- [ ] **Step 1: Create `services/frontend/src/pages/compliance/GenerateTab.jsx`**

```jsx
import React, { useState } from 'react';
import {
  Box, Flex, Wrap, WrapItem, Button, Select, Input, FormControl,
  FormLabel, FormErrorMessage, Text, useToast,
} from '@chakra-ui/react';
import api from '../../services/api';
import { FRAMEWORKS, FORMAT_LABELS, daysAgo, today } from './complianceUtils';

/**
 * GenerateTab — framework picker + date range + format select + submit.
 * Calls onCreated(reportId) on success and switches parent to History tab.
 */
const GenerateTab = ({ onCreated }) => {
  const toast = useToast();
  const [framework, setFramework] = useState('');
  const [format, setFormat] = useState('pdf');
  const [startDate, setStartDate] = useState(daysAgo(365));
  const [endDate, setEndDate] = useState(today());
  const [dateError, setDateError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const validateDates = (start, end) => {
    if (end <= start) {
      setDateError('End date must be after start date');
      return false;
    }
    setDateError('');
    return true;
  };

  const handleStartChange = (e) => {
    setStartDate(e.target.value);
    validateDates(e.target.value, endDate);
  };

  const handleEndChange = (e) => {
    setEndDate(e.target.value);
    validateDates(startDate, e.target.value);
  };

  const handleSubmit = async () => {
    if (!framework) return;
    if (!validateDates(startDate, endDate)) return;
    setIsLoading(true);
    try {
      const report = await api.createComplianceReport({
        framework,
        format,
        period_start: startDate,
        period_end: endDate,
      });
      toast({ title: 'Report generation started', status: 'success', duration: 3000, isClosable: true });
      onCreated(report.id);
    } catch (err) {
      toast({ title: 'Failed to create report', description: err.message, status: 'error', duration: 5000, isClosable: true });
    } finally {
      setIsLoading(false);
    }
  };

  const isDisabled = !framework || !!dateError || isLoading;

  return (
    <Box>
      {/* Framework picker */}
      <FormControl mb={4} isRequired>
        <FormLabel>Framework</FormLabel>
        <Wrap spacing={2}>
          {FRAMEWORKS.map(({ id, label, colorScheme }) => (
            <WrapItem key={id}>
              <Button
                size="sm"
                colorScheme={colorScheme}
                variant={framework === id ? 'solid' : 'outline'}
                onClick={() => setFramework(id)}
                aria-pressed={framework === id}
              >
                {label}
              </Button>
            </WrapItem>
          ))}
        </Wrap>
        {!framework && (
          <Text fontSize="xs" color="gray.500" mt={1}>Select a framework to continue</Text>
        )}
      </FormControl>

      {/* Date range */}
      <Flex gap={4} mb={4} flexWrap="wrap">
        <FormControl maxW="200px" isInvalid={!!dateError}>
          <FormLabel>Period Start</FormLabel>
          <Input
            type="date"
            value={startDate}
            onChange={handleStartChange}
            aria-label="Period start date"
          />
        </FormControl>
        <FormControl maxW="200px" isInvalid={!!dateError}>
          <FormLabel>Period End</FormLabel>
          <Input
            type="date"
            value={endDate}
            onChange={handleEndChange}
            aria-label="Period end date"
          />
          {dateError && <FormErrorMessage>{dateError}</FormErrorMessage>}
        </FormControl>
      </Flex>

      {/* Format */}
      <FormControl maxW="180px" mb={6}>
        <FormLabel>Format</FormLabel>
        <Select
          value={format}
          onChange={(e) => setFormat(e.target.value)}
          aria-label="Report format"
        >
          {Object.entries(FORMAT_LABELS).map(([val, label]) => (
            <option key={val} value={val}>{label}</option>
          ))}
        </Select>
      </FormControl>

      <Button
        colorScheme="blue"
        isDisabled={isDisabled}
        isLoading={isLoading}
        loadingText="Generating…"
        onClick={handleSubmit}
      >
        Generate Report
      </Button>
    </Box>
  );
};

export default GenerateTab;
```

---

### Task 13: HistoryTab.jsx

**Files:**
- Create: `services/frontend/src/pages/compliance/HistoryTab.jsx`

- [ ] **Step 1: Create `services/frontend/src/pages/compliance/HistoryTab.jsx`**

```jsx
import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Table, Thead, Tbody, Tr, Th, Td, Badge, Spinner, Button,
  Text, Flex, useToast,
} from '@chakra-ui/react';
import api from '../../services/api';
import { STATUS_COLORS, FORMAT_LABELS, isTerminalStatus } from './complianceUtils';
import { useReportPolling } from './useReportPolling';

/**
 * HistoryTab — shows the list of compliance reports with live status updates.
 * triggerReload is a counter that increments when a new report is created,
 * causing this tab to re-fetch the list.
 */
const HistoryTab = ({ triggerReload }) => {
  const toast = useToast();
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);

  const loadReports = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listComplianceReports();
      setReports(data.items || []);
    } catch (err) {
      toast({ title: 'Failed to load reports', description: err.message, status: 'error', duration: 4000, isClosable: true });
    } finally {
      setLoading(false);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    loadReports();
  }, [loadReports, triggerReload]);

  const handleUpdate = useCallback((refreshed) => {
    setReports(refreshed);
  }, []);

  useReportPolling(reports, handleUpdate);

  const handleDownload = async (reportId) => {
    try {
      const fresh = await api.getComplianceReport(reportId);
      if (fresh.download_url) {
        window.open(fresh.download_url, '_blank', 'noopener,noreferrer');
      }
    } catch (err) {
      toast({ title: 'Download failed', description: err.message, status: 'error', duration: 4000, isClosable: true });
    }
  };

  const handleRetry = async (report) => {
    const params = report.parameters || {};
    try {
      await api.createComplianceReport({
        framework: report.framework,
        format: report.format,
        period_start: params.period_start || '',
        period_end: params.period_end || '',
      });
      toast({ title: 'Report queued for retry', status: 'info', duration: 3000, isClosable: true });
      loadReports();
    } catch (err) {
      toast({ title: 'Retry failed', description: err.message, status: 'error', duration: 4000, isClosable: true });
    }
  };

  if (loading) {
    return (
      <Flex justify="center" py={8}><Spinner /></Flex>
    );
  }

  if (!reports.length) {
    return (
      <Box py={8} textAlign="center" color="gray.500">
        No reports yet. Use the Generate tab to create your first report.
      </Box>
    );
  }

  return (
    <Box overflowX="auto">
      <Table size="sm" variant="simple">
        <Thead>
          <Tr>
            <Th>Framework</Th>
            <Th>Format</Th>
            <Th>Status</Th>
            <Th>Started</Th>
            <Th>Action</Th>
          </Tr>
        </Thead>
        <Tbody>
          {reports.map((report) => (
            <Tr key={report.id}>
              <Td fontWeight="medium">{report.framework?.toUpperCase().replace('_', ' ')}</Td>
              <Td>{FORMAT_LABELS[report.format] || report.format}</Td>
              <Td>
                <Flex align="center" gap={2}>
                  {!isTerminalStatus(report.status) && <Spinner size="xs" />}
                  <Badge colorScheme={STATUS_COLORS[report.status] || 'gray'}>
                    {report.status}
                  </Badge>
                </Flex>
              </Td>
              <Td fontSize="xs" color="gray.500">
                {report.created_at
                  ? new Date(report.created_at).toLocaleDateString()
                  : '—'}
              </Td>
              <Td>
                {report.status === 'completed' && (
                  <Button size="xs" colorScheme="teal" onClick={() => handleDownload(report.id)}>
                    Download
                  </Button>
                )}
                {report.status === 'failed' && (
                  <Button size="xs" colorScheme="orange" variant="outline"
                          onClick={() => handleRetry(report)}>
                    Retry
                  </Button>
                )}
                {!isTerminalStatus(report.status) && (
                  <Text fontSize="xs" color="gray.400">Pending…</Text>
                )}
              </Td>
            </Tr>
          ))}
        </Tbody>
      </Table>
    </Box>
  );
};

export default HistoryTab;
```

---

### Task 14: ComplianceViewer.jsx and all compliance tests

**Files:**
- Modify: `services/frontend/src/pages/compliance/ComplianceViewer.jsx` (replace stub)
- Create: `services/frontend/src/__tests__/ComplianceViewer.test.jsx`

- [ ] **Step 1: Replace stub with full `ComplianceViewer.jsx`**

```jsx
import React, { useState } from 'react';
import {
  Box, Heading, Tabs, TabList, Tab, TabPanels, TabPanel,
} from '@chakra-ui/react';
import GenerateTab from './GenerateTab';
import HistoryTab from './HistoryTab';

const ComplianceViewer = () => {
  const [tabIndex, setTabIndex] = useState(0);
  const [reloadFlag, setReloadFlag] = useState(0);

  const handleCreated = () => {
    setReloadFlag((f) => f + 1);
    setTabIndex(1);
  };

  return (
    <Box p={6}>
      <Heading size="lg" mb={6}>Compliance Reports</Heading>
      <Tabs index={tabIndex} onChange={setTabIndex} variant="enclosed">
        <TabList>
          <Tab>Generate</Tab>
          <Tab>History</Tab>
        </TabList>
        <TabPanels>
          <TabPanel>
            <GenerateTab onCreated={handleCreated} />
          </TabPanel>
          <TabPanel>
            <HistoryTab triggerReload={reloadFlag} />
          </TabPanel>
        </TabPanels>
      </Tabs>
    </Box>
  );
};

export default ComplianceViewer;
```

- [ ] **Step 2: Create `services/frontend/src/__tests__/ComplianceViewer.test.jsx`**

```jsx
import React from 'react';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders, setAuthRole } from '../test-utils';
import ComplianceViewer from '../pages/compliance/ComplianceViewer';
import api from '../services/api';

jest.mock('../services/api', () => ({
  __esModule: true,
  default: {
    getMspOverview: jest.fn(),
    setActiveOrg: jest.fn(),
    createComplianceReport: jest.fn(),
    listComplianceReports: jest.fn(),
    getComplianceReport: jest.fn(),
  },
}));

const MOCK_REPORTS = [
  {
    id: 'rpt-1', framework: 'pci_dss', format: 'pdf',
    status: 'completed', created_at: '2026-03-01T10:00:00Z', download_url: null,
  },
  {
    id: 'rpt-2', framework: 'hipaa', format: 'docx',
    status: 'pending', created_at: '2026-03-02T10:00:00Z', download_url: null,
  },
];

afterEach(() => { jest.clearAllMocks(); localStorage.clear(); });

test('renders Generate tab by default', async () => {
  api.getMspOverview.mockRejectedValue(new Error('403'));
  api.listComplianceReports.mockResolvedValue({ items: [], total: 0, skip: 0, limit: 20 });
  setAuthRole('engineer');
  renderWithProviders(<ComplianceViewer />);
  expect(screen.getByRole('tab', { name: /generate/i })).toBeInTheDocument();
  expect(screen.getByRole('tab', { name: /history/i })).toBeInTheDocument();
  expect(screen.getByText(/framework/i)).toBeInTheDocument();
});

test('framework pill selection — clicking one activates it', async () => {
  api.getMspOverview.mockRejectedValue(new Error('403'));
  api.listComplianceReports.mockResolvedValue({ items: [], total: 0, skip: 0, limit: 20 });
  setAuthRole('engineer');
  renderWithProviders(<ComplianceViewer />);
  const pciBtn = screen.getByRole('button', { name: /PCI-DSS/i });
  await userEvent.click(pciBtn);
  expect(pciBtn).toHaveAttribute('aria-pressed', 'true');
});

test('submit disabled until framework selected', async () => {
  api.getMspOverview.mockRejectedValue(new Error('403'));
  api.listComplianceReports.mockResolvedValue({ items: [], total: 0, skip: 0, limit: 20 });
  setAuthRole('engineer');
  renderWithProviders(<ComplianceViewer />);
  const submitBtn = screen.getByRole('button', { name: /generate report/i });
  expect(submitBtn).toBeDisabled();
});

test('date validation: end before start shows error and blocks submit', async () => {
  api.getMspOverview.mockRejectedValue(new Error('403'));
  api.listComplianceReports.mockResolvedValue({ items: [], total: 0, skip: 0, limit: 20 });
  setAuthRole('engineer');
  renderWithProviders(<ComplianceViewer />);

  const pciBtn = screen.getByRole('button', { name: /PCI-DSS/i });
  await userEvent.click(pciBtn);

  const startInput = screen.getByLabelText(/period start date/i);
  const endInput = screen.getByLabelText(/period end date/i);
  await userEvent.clear(startInput);
  await userEvent.type(startInput, '2025-12-01');
  await userEvent.clear(endInput);
  await userEvent.type(endInput, '2025-01-01');

  expect(screen.getByText(/end date must be after/i)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /generate report/i })).toBeDisabled();
});

test('successful submit calls api.createComplianceReport and switches to History tab', async () => {
  api.getMspOverview.mockRejectedValue(new Error('403'));
  api.createComplianceReport.mockResolvedValue({
    id: 'rpt-new', status: 'pending', framework: 'pci_dss', format: 'pdf',
  });
  api.listComplianceReports.mockResolvedValue({ items: [], total: 0, skip: 0, limit: 20 });
  setAuthRole('engineer');
  renderWithProviders(<ComplianceViewer />);

  await userEvent.click(screen.getByRole('button', { name: /PCI-DSS/i }));
  await userEvent.click(screen.getByRole('button', { name: /generate report/i }));

  await waitFor(() => {
    expect(api.createComplianceReport).toHaveBeenCalledWith(
      expect.objectContaining({ framework: 'pci_dss' })
    );
  });

  // Should switch to History tab
  await waitFor(() => {
    expect(screen.getByRole('tab', { name: /history/i }))
      .toHaveAttribute('aria-selected', 'true');
  });
});

test('History tab shows report rows with status badges', async () => {
  api.getMspOverview.mockRejectedValue(new Error('403'));
  api.listComplianceReports.mockResolvedValue({ items: MOCK_REPORTS, total: 2, skip: 0, limit: 20 });
  setAuthRole('engineer');
  renderWithProviders(<ComplianceViewer />);

  // Switch to History tab
  await userEvent.click(screen.getByRole('tab', { name: /history/i }));

  await waitFor(() => {
    expect(screen.getByText(/pci/i)).toBeInTheDocument();
    expect(screen.getByText(/completed/i)).toBeInTheDocument();
    expect(screen.getByText(/pending/i)).toBeInTheDocument();
  });
});

test('completed report shows Download button', async () => {
  api.getMspOverview.mockRejectedValue(new Error('403'));
  api.listComplianceReports.mockResolvedValue({ items: MOCK_REPORTS, total: 2, skip: 0, limit: 20 });
  setAuthRole('engineer');
  renderWithProviders(<ComplianceViewer />);

  await userEvent.click(screen.getByRole('tab', { name: /history/i }));
  await waitFor(() => {
    expect(screen.getByRole('button', { name: /download/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run compliance tests**

```bash
cd /home/openether/NetDiscoverIT/services/frontend
npm test -- --watchAll=false --testPathPattern="ComplianceViewer"
```
Expected: all 7 tests PASS

- [ ] **Step 4: Commit**

```bash
git add services/frontend/src/pages/compliance/ \
        services/frontend/src/__tests__/ComplianceViewer.test.jsx
git commit -m "feat(compliance): add ComplianceViewer with Generate/History tabs, polling, and tests"
```

---

### Task 15: assistantUtils.js and SourceCard.jsx

**Files:**
- Create: `services/frontend/src/pages/assistant/assistantUtils.js`
- Create: `services/frontend/src/pages/assistant/SourceCard.jsx`

- [ ] **Step 1: Create `services/frontend/src/pages/assistant/assistantUtils.js`**

```js
export const QUERY_TYPE_COLORS = {
  topology:   'blue',
  security:   'red',
  compliance: 'orange',
  changes:    'purple',
  inventory:  'gray',
};

/** Returns a Chakra colorScheme string based on a 0–1 confidence score. */
export function confidenceColor(score) {
  if (score >= 0.8) return 'green';
  if (score >= 0.5) return 'yellow';
  return 'red';
}
```

- [ ] **Step 2: Create `services/frontend/src/pages/assistant/SourceCard.jsx`**

```jsx
import React from 'react';
import { Tag, TagLabel } from '@chakra-ui/react';
import { Link } from 'react-router-dom';

/**
 * SourceCard — clickable device chip showing hostname and similarity score.
 * Links to the /devices page (no per-device route yet).
 */
const SourceCard = ({ hostname, similarity }) => (
  <Tag
    as={Link}
    to="/devices"
    size="sm"
    colorScheme="blue"
    variant="subtle"
    cursor="pointer"
    _hover={{ opacity: 0.8 }}
  >
    <TagLabel>
      {hostname} · {Math.round((similarity || 0) * 100)}%
    </TagLabel>
  </Tag>
);

export default SourceCard;
```

---

### Task 16: ChatMessage.jsx

**Files:**
- Create: `services/frontend/src/pages/assistant/ChatMessage.jsx`

- [ ] **Step 1: Create `services/frontend/src/pages/assistant/ChatMessage.jsx`**

```jsx
import React from 'react';
import {
  Box, Flex, Text, Badge, Progress, Wrap, WrapItem, Icon,
  UnorderedList, ListItem,
} from '@chakra-ui/react';
import { FiGitBranch, FiAlertTriangle } from 'react-icons/fi';
import ReactMarkdown from 'react-markdown';
import SourceCard from './SourceCard';
import { QUERY_TYPE_COLORS, confidenceColor } from './assistantUtils';

// Chakra-compatible overrides for ReactMarkdown rendering
const markdownComponents = {
  // eslint-disable-next-line react/display-name
  p: ({ children }) => <Text fontSize="sm" mb={2}>{children}</Text>,
  // eslint-disable-next-line react/display-name
  ul: ({ children }) => <UnorderedList mb={2} pl={4}>{children}</UnorderedList>,
  // eslint-disable-next-line react/display-name
  li: ({ children }) => <ListItem fontSize="sm">{children}</ListItem>,
  // eslint-disable-next-line react/display-name
  strong: ({ children }) => <Text as="span" fontWeight="bold">{children}</Text>,
};

const ChatMessage = ({ message }) => {
  // User message — right-aligned blue bubble
  if (message.role === 'user') {
    return (
      <Flex justify="flex-end" mb={4}>
        <Box
          bg="blue.500"
          color="white"
          borderRadius="lg"
          px={4}
          py={2}
          maxW="70%"
          fontSize="sm"
        >
          {message.text}
        </Box>
      </Flex>
    );
  }

  // Error message — centered red card
  if (message.role === 'error') {
    return (
      <Flex justify="flex-start" mb={4} align="center" gap={2}>
        <Icon as={FiAlertTriangle} color="red.400" />
        <Text fontSize="sm" color="red.500">{message.text}</Text>
      </Flex>
    );
  }

  // Assistant message — left-aligned white card
  const colorScheme = confidenceColor(message.confidence);
  const queryColor = QUERY_TYPE_COLORS[message.query_type] || 'gray';

  return (
    <Flex justify="flex-start" mb={4}>
      <Box
        bg="white"
        border="1px"
        borderColor="gray.200"
        borderRadius="lg"
        p={4}
        w="100%"
        boxShadow="sm"
      >
        {/* query_type badge */}
        <Flex justify="flex-end" mb={2}>
          <Badge colorScheme={queryColor} variant="subtle" textTransform="capitalize">
            {message.query_type || 'query'}
          </Badge>
        </Flex>

        {/* Answer rendered as markdown */}
        <Box mb={3}>
          {message.answer
            ? <ReactMarkdown components={markdownComponents}>{message.answer}</ReactMarkdown>
            : <Text fontSize="sm" color="gray.500">(no answer)</Text>
          }
        </Box>

        {/* Confidence bar */}
        <Flex align="center" gap={2} mb={3}>
          <Progress
            value={(message.confidence || 0) * 100}
            colorScheme={colorScheme}
            size="xs"
            flex="1"
            borderRadius="full"
          />
          <Text fontSize="xs" color="gray.500" flexShrink={0}>
            {Math.round((message.confidence || 0) * 100)}%
          </Text>
        </Flex>

        {/* Graph traversal indicator */}
        {message.graph_traversal_used && (
          <Flex align="center" gap={1} mb={2} color="gray.500">
            <Icon as={FiGitBranch} boxSize={3} />
            <Text fontSize="xs">Graph traversal used</Text>
          </Flex>
        )}

        {/* Source device chips */}
        {message.sources?.length > 0 && (
          <Wrap spacing={2}>
            {message.sources.map((src) => (
              <WrapItem key={src.device_id}>
                <SourceCard hostname={src.hostname} similarity={src.similarity} />
              </WrapItem>
            ))}
          </Wrap>
        )}
      </Box>
    </Flex>
  );
};

export default ChatMessage;
```

---

### Task 17: AssistantPage.jsx

**Files:**
- Modify: `services/frontend/src/pages/assistant/AssistantPage.jsx` (replace stub)

- [ ] **Step 1: Replace stub with full `AssistantPage.jsx`**

```jsx
import React, { useState, useRef, useCallback } from 'react';
import {
  Box, Flex, Heading, Text, Textarea, IconButton,
  Spinner, Button, useToast,
} from '@chakra-ui/react';
import { FiSend } from 'react-icons/fi';
import api from '../../services/api';
import ChatMessage from './ChatMessage';

const AssistantPage = () => {
  const toast = useToast();
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const handleSend = useCallback(async () => {
    const trimmed = question.trim();
    if (!trimmed || isLoading) return;

    const userMsg = { id: crypto.randomUUID(), role: 'user', text: trimmed };
    setMessages((prev) => [...prev, userMsg]);
    setQuestion('');
    setIsLoading(true);

    try {
      const result = await api.queryAssistant({ question: trimmed, top_k: 5 });
      const assistantMsg = {
        id: crypto.randomUUID(),
        role: 'assistant',
        answer: result.answer,
        sources: result.sources || [],
        confidence: result.confidence,
        query_type: result.query_type,
        retrieved_device_count: result.retrieved_device_count,
        graph_traversal_used: result.graph_traversal_used,
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      const errMsg = {
        id: crypto.randomUUID(),
        role: 'error',
        text: err.message === 'NLI service not available: ANTHROPIC_API_KEY is not configured'
          ? 'AI assistant is temporarily unavailable'
          : `Could not answer: ${err.message}`,
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setIsLoading(false);
      setTimeout(scrollToBottom, 50);
    }
  }, [question, isLoading]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleClear = () => setMessages([]);

  return (
    <Flex direction="column" h="100%" p={6} gap={4}>
      {/* Header */}
      <Flex justify="space-between" align="center">
        <Box>
          <Heading size="lg">Network Assistant</Heading>
          <Text fontSize="sm" color="gray.500" mt={1}>
            Ask anything about your network — devices, topology, compliance, or changes.
          </Text>
        </Box>
        {messages.length > 0 && (
          <Button size="sm" variant="ghost" onClick={handleClear}>
            Clear conversation
          </Button>
        )}
      </Flex>

      {/* Message history */}
      <Box flex="1" overflowY="auto" pr={1}>
        {messages.length === 0 && (
          <Flex h="100%" align="center" justify="center" direction="column" gap={3} color="gray.400">
            <Text fontSize="lg">Ask a question to get started</Text>
            <Text fontSize="sm">e.g. "Which devices are in PCI scope?" or "Show me my routers"</Text>
          </Flex>
        )}
        {messages.map((msg) => (
          <ChatMessage key={msg.id} message={msg} />
        ))}
        {isLoading && (
          <Flex justify="flex-start" mb={4} align="center" gap={2}>
            <Spinner size="sm" />
            <Text fontSize="sm" color="gray.500">Thinking…</Text>
          </Flex>
        )}
        <div ref={messagesEndRef} />
      </Box>

      {/* Input bar */}
      <Flex gap={2} align="flex-end" flexShrink={0}>
        <Textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about your network… (Enter to send, Shift+Enter for newline)"
          rows={1}
          resize="none"
          maxH="80px"
          overflowY="auto"
          flex="1"
          isDisabled={isLoading}
          aria-label="Chat input"
        />
        <IconButton
          aria-label="Send message"
          icon={isLoading ? <Spinner size="sm" /> : <FiSend />}
          colorScheme="blue"
          isDisabled={!question.trim() || isLoading}
          onClick={handleSend}
          flexShrink={0}
        />
      </Flex>
    </Flex>
  );
};

export default AssistantPage;
```

---

### Task 18: AssistantPage tests and integration test

**Files:**
- Create: `services/frontend/src/__tests__/AssistantPage.test.jsx`
- Create: `services/frontend/src/__tests__/integration/TopologyCompliance.test.jsx`

- [ ] **Step 1: Create `services/frontend/src/__tests__/AssistantPage.test.jsx`**

`react-markdown` is mocked to avoid ESM issues in Jest (CRA uses CommonJS Jest transform).

```jsx
import React from 'react';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders, setAuthRole } from '../test-utils';
import AssistantPage from '../pages/assistant/AssistantPage';
import api from '../services/api';

// react-markdown is ESM-only — mock it for CRA's CommonJS Jest environment
jest.mock('react-markdown', () => ({
  __esModule: true,
  default: ({ children }) => <div data-testid="markdown">{children}</div>,
}));

jest.mock('../services/api', () => ({
  __esModule: true,
  default: {
    getMspOverview: jest.fn(),
    setActiveOrg: jest.fn(),
    queryAssistant: jest.fn(),
  },
}));

const MOCK_RESPONSE = {
  answer: 'Two routers found in PCI scope: RTR-CORE-1, FW-EDGE-1.',
  sources: [
    { device_id: 'd1', hostname: 'RTR-CORE-1', similarity: 0.94 },
    { device_id: 'd2', hostname: 'FW-EDGE-1',  similarity: 0.87 },
  ],
  confidence: 0.92,
  query_type: 'compliance',
  retrieved_device_count: 2,
  graph_traversal_used: true,
};

afterEach(() => { jest.clearAllMocks(); localStorage.clear(); });

test('renders empty state prompt', () => {
  api.getMspOverview.mockRejectedValue(new Error('403'));
  setAuthRole('engineer');
  renderWithProviders(<AssistantPage />);
  expect(screen.getByText(/ask a question to get started/i)).toBeInTheDocument();
});

test('user message appears in thread after send', async () => {
  api.getMspOverview.mockRejectedValue(new Error('403'));
  api.queryAssistant.mockResolvedValue(MOCK_RESPONSE);
  setAuthRole('engineer');
  renderWithProviders(<AssistantPage />);

  const input = screen.getByLabelText(/chat input/i);
  await userEvent.type(input, 'Which routers are in PCI scope?');
  await userEvent.click(screen.getByLabelText(/send message/i));

  expect(screen.getByText('Which routers are in PCI scope?')).toBeInTheDocument();
});

test('textarea cleared after submit', async () => {
  api.getMspOverview.mockRejectedValue(new Error('403'));
  api.queryAssistant.mockResolvedValue(MOCK_RESPONSE);
  setAuthRole('engineer');
  renderWithProviders(<AssistantPage />);

  const input = screen.getByLabelText(/chat input/i);
  await userEvent.type(input, 'Hello');
  await userEvent.click(screen.getByLabelText(/send message/i));

  expect(input).toHaveValue('');
});

test('send button disabled while loading', async () => {
  api.getMspOverview.mockRejectedValue(new Error('403'));
  api.queryAssistant.mockReturnValue(new Promise(() => {})); // never resolves
  setAuthRole('engineer');
  renderWithProviders(<AssistantPage />);

  const input = screen.getByLabelText(/chat input/i);
  await userEvent.type(input, 'Test question');
  const sendBtn = screen.getByLabelText(/send message/i);
  await userEvent.click(sendBtn);

  expect(sendBtn).toBeDisabled();
});

test('assistant response rendered with source chips and confidence bar', async () => {
  api.getMspOverview.mockRejectedValue(new Error('403'));
  api.queryAssistant.mockResolvedValue(MOCK_RESPONSE);
  setAuthRole('engineer');
  renderWithProviders(<AssistantPage />);

  const input = screen.getByLabelText(/chat input/i);
  await userEvent.type(input, 'Which routers?');
  await userEvent.click(screen.getByLabelText(/send message/i));

  // Answer text rendered via mocked react-markdown
  expect(await screen.findByText(/Two routers found/i)).toBeInTheDocument();
  // Source chips
  expect(screen.getByText(/RTR-CORE-1/)).toBeInTheDocument();
  expect(screen.getByText(/FW-EDGE-1/)).toBeInTheDocument();
  // Confidence badge present (Progress component renders)
  expect(screen.getByText('92%')).toBeInTheDocument();
});

test('error response renders red error message', async () => {
  api.getMspOverview.mockRejectedValue(new Error('403'));
  api.queryAssistant.mockRejectedValue(new Error('NLI pipeline error: timeout'));
  setAuthRole('engineer');
  renderWithProviders(<AssistantPage />);

  const input = screen.getByLabelText(/chat input/i);
  await userEvent.type(input, 'Test');
  await userEvent.click(screen.getByLabelText(/send message/i));

  expect(await screen.findByText(/Could not answer/i)).toBeInTheDocument();
});

test('Enter key submits the message', async () => {
  api.getMspOverview.mockRejectedValue(new Error('403'));
  api.queryAssistant.mockResolvedValue(MOCK_RESPONSE);
  setAuthRole('engineer');
  renderWithProviders(<AssistantPage />);

  const input = screen.getByLabelText(/chat input/i);
  await userEvent.type(input, 'Router count{enter}');

  await waitFor(() => expect(api.queryAssistant).toHaveBeenCalledOnce());
});

test('Clear conversation button empties message list', async () => {
  api.getMspOverview.mockRejectedValue(new Error('403'));
  api.queryAssistant.mockResolvedValue(MOCK_RESPONSE);
  setAuthRole('engineer');
  renderWithProviders(<AssistantPage />);

  const input = screen.getByLabelText(/chat input/i);
  await userEvent.type(input, 'Hello');
  await userEvent.click(screen.getByLabelText(/send message/i));
  await screen.findByText('Hello');

  const clearBtn = screen.getByRole('button', { name: /clear conversation/i });
  await userEvent.click(clearBtn);

  expect(screen.queryByText('Hello')).not.toBeInTheDocument();
  expect(screen.getByText(/ask a question to get started/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Create integration test `services/frontend/src/__tests__/integration/TopologyCompliance.test.jsx`**

```jsx
import React from 'react';
import { screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders, setAuthRole } from '../test-utils';
import ComplianceViewer from '../pages/compliance/ComplianceViewer';
import api from '../services/api';

jest.mock('../services/api', () => ({
  __esModule: true,
  default: {
    getMspOverview: jest.fn(),
    setActiveOrg: jest.fn(),
    createComplianceReport: jest.fn(),
    listComplianceReports: jest.fn(),
    getComplianceReport: jest.fn(),
  },
}));

afterEach(() => { jest.clearAllMocks(); localStorage.clear(); });

test('full compliance flow: generate → see pending → poll resolves → Download appears', async () => {
  jest.useFakeTimers();

  const pendingReport = {
    id: 'rpt-flow-1', framework: 'pci_dss', format: 'pdf',
    status: 'pending', created_at: new Date().toISOString(),
  };
  const completedReport = { ...pendingReport, status: 'completed' };

  api.getMspOverview.mockRejectedValue(new Error('403'));
  // Initial list load (before generation) — empty
  api.listComplianceReports.mockResolvedValueOnce({ items: [], total: 0, skip: 0, limit: 20 });
  // After generation — pending appears
  api.createComplianceReport.mockResolvedValue(pendingReport);
  // History tab re-fetch after switch
  api.listComplianceReports.mockResolvedValueOnce({ items: [pendingReport], total: 1, skip: 0, limit: 20 });
  // Polling tick — completed
  api.listComplianceReports.mockResolvedValue({ items: [completedReport], total: 1, skip: 0, limit: 20 });

  setAuthRole('admin');
  renderWithProviders(<ComplianceViewer />);

  // Select framework and submit
  await userEvent.click(screen.getByRole('button', { name: /PCI-DSS/i }));
  await userEvent.click(screen.getByRole('button', { name: /generate report/i }));

  // Should switch to History tab with pending row
  await waitFor(() =>
    expect(screen.getByRole('tab', { name: /history/i }))
      .toHaveAttribute('aria-selected', 'true')
  );
  expect(await screen.findByText(/pending/i)).toBeInTheDocument();

  // Advance polling timer by 3 seconds
  await act(async () => {
    jest.advanceTimersByTime(3000);
    await Promise.resolve();
  });

  // Download button should appear after poll returns completed
  await waitFor(() =>
    expect(screen.getByRole('button', { name: /download/i })).toBeInTheDocument()
  );

  jest.useRealTimers();
});
```

- [ ] **Step 3: Run all tests**

```bash
cd /home/openether/NetDiscoverIT/services/frontend
npm test -- --watchAll=false
```
Expected output:
```
Test Suites: 9 passed, 9 total
Tests:       XX passed, XX total
```
All tests pass (no failures).

- [ ] **Step 4: Commit**

```bash
git add services/frontend/src/pages/assistant/ \
        services/frontend/src/__tests__/AssistantPage.test.jsx \
        services/frontend/src/__tests__/integration/TopologyCompliance.test.jsx
git commit -m "feat(assistant): add AssistantPage with chat history, markdown rendering, source chips, and tests"
```

- [ ] **Step 5: Update claw-memory**

```bash
cd /tmp/claw-memory
# Update current-state.md: add Group 9b completion note under "Recently Completed (2026-03-28)"
git add -A
git commit -m "update: Group 9b frontend complete (topology map, compliance viewer, NLI chat)"
git push
```

---

## Self-Review

### 1. Spec coverage

| Spec requirement | Task |
|---|---|
| `GET /api/v1/topology` endpoint | Task 2 |
| Devices from PostgreSQL (device_role, compliance_scope) | Task 2 |
| Neo4j device-to-device connection collapse | Task 1 (`get_device_connections`) |
| Backend tests (unauthenticated, device type mapping, Neo4j failure) | Task 3 |
| api.js: 5 new methods | Task 4 |
| App.js: 3 new routes | Task 5 |
| Sidebar: 3 new NavItems | Task 5 |
| `topologyUtils.js` (getNodeStyle, getBadgeColor, truncate, COMPLIANCE_SCOPE_OPTIONS) | Task 6 |
| `useTopology.js` hook (fetch, hostname filter, scope filter, reload) | Task 7 |
| TopologyMap: D3 force simulation, custom node shapes, compliance badges | Task 8 |
| TopologyMap: filter bar (hostname search + scope dropdown) | Task 8 |
| TopologyMap: node detail popover | Task 8 |
| TopologyMap: legend overlay | Task 8 |
| TopologyMap: loading/error/empty states | Task 8 |
| TopologyMap tests (spinner, SVG, error, retry, empty state, filter bar) | Task 9 |
| `complianceUtils.js` (FRAMEWORKS, STATUS_COLORS, isTerminalStatus, daysAgo) | Task 10 |
| `useReportPolling.js` (interval stops when all terminal) | Task 11 |
| GenerateTab: framework pills, date validation, format select, submit | Task 12 |
| HistoryTab: status badges, spinner for pending, Download/Retry actions | Task 13 |
| ComplianceViewer: two-tab layout, tab switching on success | Task 14 |
| Compliance tests (pill, date validation, submit, tab switch, badges, download) | Task 14 |
| `assistantUtils.js` (QUERY_TYPE_COLORS, confidenceColor) | Task 15 |
| SourceCard: chip with hostname + %, links to /devices | Task 15 |
| ChatMessage: user bubble, assistant card, markdown, confidence bar, graph indicator, chips | Task 16 |
| AssistantPage: message history, input bar, send logic, clear, Enter key | Task 17 |
| react-markdown mock in tests | Task 18 |
| AssistantPage tests (7 tests: empty state, send, clear, error, Enter) | Task 18 |
| Integration test: generate → History tab → poll → Download | Task 18 |

All spec requirements covered. ✓

### 2. Placeholder scan

No "TBD", "TODO", "implement later", or "Similar to Task N" patterns found. All code blocks are complete. ✓

### 3. Type consistency

- `useTopology` returns `{ nodes, edges, loading, error, reload, setHostnameFilter, setScopeFilter }` — all consumed correctly in `TopologyMap.jsx`. ✓
- `getNodeStyle(deviceType)` returns `{ shape, fill, r?, size?, w?, h? }` — all shape branches in TopologyMap handle all properties. ✓
- `getBadgeColor(complianceScope)` — called with `d.compliance_scope` (array) in TopologyMap D3 effect. ✓
- `useReportPolling(reports, onUpdate)` — called in HistoryTab with `reports` state array and `handleUpdate` callback. ✓
- `isTerminalStatus(status)` — used in `useReportPolling` and `HistoryTab` action column logic. ✓
- `confidenceColor(score)` — used in `ChatMessage.jsx` for `<Progress>` colorScheme. ✓
- `QUERY_TYPE_COLORS[message.query_type]` — ChatMessage accesses `message.query_type` (set from API `result.query_type`). ✓
- `handleCreated` in `ComplianceViewer` receives `report.id` from `GenerateTab`'s `onCreated(report.id)` — but `handleCreated` now takes no argument (just increments `reloadFlag`). No argument mismatch. ✓
