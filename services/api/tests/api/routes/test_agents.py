import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


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
