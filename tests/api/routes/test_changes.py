"""Tests for change record rate limiting — verifies SlowAPI can extract client IP."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


@pytest.mark.parametrize("endpoint,body_key", [
    ("/changes/00000000-0000-0000-0000-000000000001/propose", "ChangeProposeRequest"),
    ("/changes/00000000-0000-0000-0000-000000000001/approve", "ChangeApproveRequest"),
    ("/changes/00000000-0000-0000-0000-000000000001/implement", "ChangeImplementRequest"),
    ("/changes/00000000-0000-0000-0000-000000000001/verify", "ChangeVerifyRequest"),
    ("/changes/00000000-0000-0000-0000-000000000001/rollback", "ChangeRollbackRequest"),
    ("/changes/00000000-0000-0000-0000-000000000001/sync-ticket", "ChangeSyncTicketRequest"),
])
def test_change_lifecycle_endpoint_accepts_request_object(client, endpoint, body_key):
    """Rate-limited endpoints must accept fastapi.Request as first param.
    
    If SlowAPI cannot find request: Request, it raises AttributeError before
    the route handler body executes. A 404 or 403 means the route was reached;
    a 500 with 'object has no attribute' means SlowAPI broke.
    """
    response = client.post(endpoint, json={}, headers={"Authorization": "Bearer fake"})
    assert response.status_code != 500, (
        f"Got 500 — SlowAPI likely failed to find request: Request. "
        f"Response: {response.text}"
    )
