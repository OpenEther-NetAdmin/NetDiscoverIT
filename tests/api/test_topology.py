"""
Unit tests for GET /api/v1/topology endpoint
"""
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

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
    dev1 = _make_device(hostname="RTR-CORE-1", role="core_router", scope=["PCI-CDE"])
    dev2 = _make_device(hostname="SW-ACCESS-1", role="access_switch")

    mock_neo4j = MagicMock()
    mock_neo4j.get_device_connections = AsyncMock(return_value=[
        {"source": str(dev1.id), "target": str(dev2.id)}
    ])
    monkeypatch.setattr("app.api.routes.topology.get_neo4j_client",
                        AsyncMock(return_value=mock_neo4j))

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
    pci_node = next(n for n in data["nodes"] if n["hostname"] == "RTR-CORE-1")
    assert pci_node["compliance_scope"] == ["PCI-CDE"]


def test_topology_device_type_mapping(monkeypatch):
    devices = [
        _make_device(hostname="R1",   role="core_router"),
        _make_device(hostname="SW1",  role="distribution_switch"),
        _make_device(hostname="FW1",  role="edge_firewall"),
        _make_device(hostname="SRV1", role="app_server"),
        _make_device(hostname="X1",   role=None),
    ]

    mock_neo4j = MagicMock()
    mock_neo4j.get_device_connections = AsyncMock(return_value=[])
    monkeypatch.setattr("app.api.routes.topology.get_neo4j_client",
                        AsyncMock(return_value=mock_neo4j))

    app.dependency_overrides[get_current_user] = lambda: MOCK_USER
    app.dependency_overrides[get_db] = _db_override(devices)
    try:
        resp = client.get("/api/v1/topology")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    type_map = {n["hostname"]: n["device_type"] for n in resp.json()["nodes"]}
    assert type_map["R1"]   == "router"
    assert type_map["SW1"]  == "switch"
    assert type_map["FW1"]  == "firewall"
    assert type_map["SRV1"] == "server"
    assert type_map["X1"]   == "unknown"


def test_topology_neo4j_failure_returns_nodes_no_edges(monkeypatch):
    dev1 = _make_device()

    monkeypatch.setattr("app.api.routes.topology.get_neo4j_client",
                        AsyncMock(side_effect=RuntimeError("Neo4j down")))

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


def test_topology_empty_org(monkeypatch):
    mock_neo4j = MagicMock()
    mock_neo4j.get_device_connections = AsyncMock(return_value=[])
    monkeypatch.setattr("app.api.routes.topology.get_neo4j_client",
                        AsyncMock(return_value=mock_neo4j))

    app.dependency_overrides[get_current_user] = lambda: MOCK_USER
    app.dependency_overrides[get_db] = _db_override([])
    try:
        resp = client.get("/api/v1/topology")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["node_count"] == 0
    assert data["edge_count"] == 0
    assert data["nodes"] == []
    assert data["edges"] == []
