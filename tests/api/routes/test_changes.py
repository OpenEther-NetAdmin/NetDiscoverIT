"""Tests for change record rate limiting and webhook HMAC verification."""
import pytest
import hmac
import hashlib
import json
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.mark.parametrize("endpoint,body_key", [
    ("/api/v1/changes/00000000-0000-0000-0000-000000000001/propose", "ChangeProposeRequest"),
    ("/api/v1/changes/00000000-0000-0000-0000-000000000001/approve", "ChangeApproveRequest"),
    ("/api/v1/changes/00000000-0000-0000-0000-000000000001/implement", "ChangeImplementRequest"),
    ("/api/v1/changes/00000000-0000-0000-0000-000000000001/verify", "ChangeVerifyRequest"),
    ("/api/v1/changes/00000000-0000-0000-0000-000000000001/rollback", "ChangeRollbackRequest"),
    ("/api/v1/changes/00000000-0000-0000-0000-000000000001/sync-ticket", "ChangeSyncTicketRequest"),
])
@pytest.mark.asyncio
async def test_change_lifecycle_endpoint_accepts_request_object(endpoint, body_key):
    """Rate-limited endpoints must accept fastapi.Request as first param.
    
    If SlowAPI cannot find request: Request, it raises AttributeError before
    the route handler body executes. A 404 or 403 means the route was reached;
    a 500 with 'object has no attribute' means SlowAPI broke.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(endpoint, json={}, headers={"Authorization": "Bearer fake"})
        assert response.status_code != 500, (
            f"Got 500 — SlowAPI likely failed to find request: Request. "
            f"Response: {response.text}"
        )


@pytest.mark.asyncio
async def test_webhook_rejects_missing_signature():
    """Webhook must reject requests with no HMAC signature header."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/webhooks/change/00000000-0000-0000-0000-000000000099",
            json={"sys_id": "CHG001", "state": "approved"},
        )
        assert response.status_code in (401, 403, 404), (
            f"Expected 401/403/404, got {response.status_code}. "
            "Webhook accepted an unsigned request."
        )


@pytest.mark.asyncio
async def test_webhook_rejects_invalid_signature():
    """Webhook must reject requests with a bad HMAC signature."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/webhooks/change/00000000-0000-0000-0000-000000000099",
            json={"sys_id": "CHG001", "state": "approved"},
            headers={"X-Webhook-Signature": "sha256=badsignature"},
        )
        assert response.status_code in (401, 403, 404), (
            f"Expected 401/403/404 for bad signature, got {response.status_code}."
        )
