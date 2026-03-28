"""
Tests for agent heartbeat endpoint - Task 1.3 test coverage.

These tests verify:
1. Heartbeat succeeds with valid X-Agent-Key
2. Agent from Org A cannot heartbeat Org B's agent (org isolation)
"""

import pytest
import pytest_asyncio
from uuid import uuid4
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.db.database import async_session_maker
from app.models.models import LocalAgent, Organization
from app.core.security import hash_password


@pytest_asyncio.fixture
async def org_a():
    """Create Organization A for testing."""
    async with async_session_maker() as session:
        org = Organization(
            id=uuid4(),
            name="Test Org A",
            slug=f"test-org-a-{uuid4().hex[:6]}",
        )
        session.add(org)
        await session.commit()
        await session.refresh(org)
        yield org
        await session.delete(org)
        await session.commit()


@pytest_asyncio.fixture
async def org_b():
    """Create Organization B for testing."""
    async with async_session_maker() as session:
        org = Organization(
            id=uuid4(),
            name="Test Org B",
            slug=f"test-org-b-{uuid4().hex[:6]}",
        )
        session.add(org)
        await session.commit()
        await session.refresh(org)
        yield org
        await session.delete(org)
        await session.commit()


@pytest_asyncio.fixture
async def agent_a(org_a):
    """Create a real agent in Org A with known API key."""
    async with async_session_maker() as session:
        api_key = "test_agent_a_key_12345"
        agent = LocalAgent(
            id=uuid4(),
            organization_id=org_a.id,
            name="Agent A",
            api_key_hash=hash_password(api_key),
            is_active=True,
            capabilities={},
        )
        session.add(agent)
        await session.commit()
        await session.refresh(agent)
        agent_id = agent.id
        yield {"agent_id": agent_id, "api_key": api_key}
        await session.delete(agent)
        await session.commit()


@pytest_asyncio.fixture
async def agent_b(org_b):
    """Create a real agent in Org B with known API key."""
    async with async_session_maker() as session:
        api_key = "test_agent_b_key_67890"
        agent = LocalAgent(
            id=uuid4(),
            organization_id=org_b.id,
            name="Agent B",
            api_key_hash=hash_password(api_key),
            is_active=True,
            capabilities={},
        )
        session.add(agent)
        await session.commit()
        await session.refresh(agent)
        agent_id = agent.id
        yield {"agent_id": agent_id, "api_key": api_key}
        await session.delete(agent)
        await session.commit()


@pytest.mark.asyncio
async def test_heartbeat_requires_agent_auth():
    """Heartbeat endpoint should require X-Agent-Key auth (agent auth, not user JWT)"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/agents/some-uuid/heartbeat",
            json={"agent_version": "1.0.0", "capabilities": ["scan"]},
            headers={"X-Agent-Key": "invalid-key"}
        )
        assert response.status_code in [401, 404], (
            f"Expected 401 or 404 (agent not found), got {response.status_code}. "
            "Heartbeat endpoint should use X-Agent-Key auth (agent auth), not user JWT. "
            "401 = invalid key, 404 = valid key but agent doesn't exist."
        )


@pytest.mark.asyncio
async def test_heartbeat_success_with_valid_agent_key(agent_a):
    """Heartbeat succeeds when called with valid X-Agent-Key for the agent."""
    agent_id = agent_a["agent_id"]
    api_key = agent_a["api_key"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/agents/{agent_id}/heartbeat",
            json={"agent_version": "1.0.0", "capabilities": {"scanner": True}},
            headers={"X-Agent-Key": api_key}
        )
        assert response.status_code == 200, (
            f"Expected 200 OK, got {response.status_code}. "
            f"Response: {response.text}. "
            "Heartbeat should succeed with valid X-Agent-Key."
        )
        data = response.json()
        assert data["status"] == "ok"
        assert data["agent_id"] == str(agent_id)
        assert "last_seen" in data


@pytest.mark.asyncio
async def test_heartbeat_cross_org_isolation(agent_a, agent_b):
    """Agent from Org A cannot heartbeat Org B's agent - org isolation enforced."""
    agent_a_key = agent_a["api_key"]
    agent_b_id = agent_b["agent_id"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/agents/{agent_b_id}/heartbeat",
            json={"agent_version": "1.0.0", "capabilities": {}},
            headers={"X-Agent-Key": agent_a_key}
        )
        assert response.status_code == 404, (
            f"Expected 404 Not Found, got {response.status_code}. "
            f"Response: {response.text}. "
            "Agent from Org A should NOT be able to heartbeat Org B's agent. "
            "This indicates org isolation is properly enforced."
        )
