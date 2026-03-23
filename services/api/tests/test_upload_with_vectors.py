import pytest
from unittest.mock import AsyncMock
from httpx import AsyncClient, ASGITransport
from uuid import UUID

FIXED_ORG_ID = "00000000-0000-0000-0000-000000000001"
FIXED_AGENT_ID = "00000000-0000-0000-0000-000000000003"


@pytest.mark.asyncio
async def test_upload_with_vectors():
    from app.main import app as fastapi_app
    from app.api import dependencies

    async def mock_get_agent_auth():
        return {
            "agent_id": FIXED_AGENT_ID,
            "organization_id": FIXED_ORG_ID,
            "agent_name": "test-agent"
        }

    fastapi_app.dependency_overrides[dependencies.get_agent_auth] = mock_get_agent_auth

    try:
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as client:
            payload = {
                "devices": [
                    {
                        "hostname": "test-router",
                        "ip_address": "10.0.0.1",
                        "device_type": "router",
                        "vendor": "Cisco",
                        "role_vector": [0.1] * 768,
                        "topology_vector": [0.2] * 768,
                        "security_vector": [0.3] * 768,
                        "config_vector": [0.4] * 768
                    }
                ]
            }
            response = await client.post(
                f"/api/v1/agents/{FIXED_AGENT_ID}/upload",
                json=payload,
                headers={"X-Agent-Key": "test-key"}
            )
            assert response.status_code in [200, 201], f"Expected 200/201 but got {response.status_code}: {response.text}"
    finally:
        fastapi_app.dependency_overrides.clear()
