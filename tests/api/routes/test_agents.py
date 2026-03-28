import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_heartbeat_requires_auth():
    """Heartbeat endpoint should require authentication"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/agents/some-uuid/heartbeat",
            json={"agent_version": "1.0.0", "capabilities": ["scan"]}
        )
        assert response.status_code == 401, (
            f"Expected 401 Unauthorized, got {response.status_code}. "
            "Heartbeat endpoint should require authentication."
        )
