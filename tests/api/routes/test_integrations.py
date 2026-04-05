"""Tests for external integration connectivity checks."""
import base64
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.routes.integrations import _test_integration


@pytest.mark.asyncio
async def test_jira_auth_header_is_base64_encoded():
    """Jira Basic auth must be base64(email:api_token), not raw token."""
    captured_headers = {}

    async def mock_get(url, headers=None, timeout=None):
        captured_headers.update(headers or {})
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        return mock_resp

    mock_integration = MagicMock()
    mock_integration.integration_type = "jira"
    mock_integration.base_url = "https://example.atlassian.net"

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(side_effect=mock_get)
        mock_client_class.return_value = mock_client

        result = await _test_integration(
            integration=mock_integration,
            credentials={"email": "user@example.com", "api_token": "mytoken123"},
            test_message=None,
        )

    assert result["success"] is True, f"Expected success, got: {result}"
    auth_header = captured_headers.get("Authorization", "")
    assert auth_header.startswith("Basic "), f"Expected 'Basic ...', got: {auth_header}"
    encoded = auth_header[6:]
    decoded = base64.b64decode(encoded).decode()
    assert decoded == "user@example.com:mytoken123", (
        f"Expected base64(email:token), got decoded: {decoded}"
    )
