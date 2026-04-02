"""
Tests for refresh token endpoint - verifies refresh_token returns string, not function.

This test file verifies the fix for a bug where the /refresh endpoint was returning
a function object instead of a token string because the endpoint function was named
'refresh_token' which shadowed the imported create_refresh_token function.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from starlette.requests import Request

from app.models.models import User


def noop_decorator(func):
    return func


class TestRefreshTokenReturnsString:
    """
    Test cases for refresh token returning actual token string.

    The bug: The refresh_token endpoint function was named 'refresh_token' which
    shadowed the create_refresh_token function. When returning TokenResponse,
    it used 'refresh_token=refresh_token' which referenced the endpoint function
    object instead of calling create_refresh_token to get the actual token string.

    The fix: Call create_refresh_token(data={"sub": str(user.id)}) to generate
    a new refresh token instead of using the shadowed variable.
    """

    @pytest.fixture
    def mock_user(self):
        user = MagicMock(spec=User)
        user.id = uuid4()
        user.email = "test@example.com"
        user.organization_id = uuid4()
        user.role = "admin"
        user.is_active = True
        user.hashed_password = "hashed_password"
        return user

    @pytest.mark.asyncio
    async def test_refresh_token_returns_string_not_function(self, mock_user):
        """
        Verify that /refresh endpoint returns refresh_token as a string, not a function.
        """
        from app.api.auth import TokenResponse

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute = AsyncMock(return_value=mock_result)

        from app.core.security import create_access_token, create_refresh_token, decode_token

        valid_token_payload = {"sub": str(mock_user.id)}
        mock_decoded_token = valid_token_payload.copy()

        with patch("app.api.auth.decode_token") as mock_decode, \
             patch("app.api.auth.create_access_token") as mock_create_access, \
             patch("app.api.auth.create_refresh_token") as mock_create_refresh:

            mock_decode.return_value = mock_decoded_token
            mock_create_access.return_value = "test_access_token"
            mock_create_refresh.return_value = "test_refresh_token_string"

            from app.api.auth import refresh_token
            from app.api.auth import RefreshTokenRequest

            mock_request = MagicMock(spec=Request)
            with patch("app.api.auth.limiter.limit", noop_decorator):
                request = RefreshTokenRequest(refresh_token="valid_refresh_token")
                response = await refresh_token(request=mock_request, refresh_req=request, db=mock_db)

            assert isinstance(response, TokenResponse)
            assert response.refresh_token == "test_refresh_token_string"
            assert not callable(response.refresh_token)

    @pytest.mark.asyncio
    async def test_refresh_token_is_not_function_object(self, mock_user):
        """
        Ensure refresh_token field is a string, not a function reference.
        """
        from app.api.auth import TokenResponse

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.api.auth.decode_token") as mock_decode, \
             patch("app.api.auth.create_access_token") as mock_create_access, \
             patch("app.api.auth.create_refresh_token") as mock_create_refresh:

            mock_decode.return_value = {"sub": str(mock_user.id)}
            mock_create_access.return_value = "access"
            mock_create_refresh.return_value = "refresh_token_value"

            from app.api.auth import refresh_token, RefreshTokenRequest

            mock_request = MagicMock(spec=Request)
            with patch("app.api.auth.limiter.limit", noop_decorator):
                result = await refresh_token(
                    request=mock_request,
                    refresh_req=RefreshTokenRequest(refresh_token="some_token"),
                    db=mock_db
                )

            assert not hasattr(result.refresh_token, "__call__"), \
                "refresh_token should not be callable - it should be a string"
            assert isinstance(result.refresh_token, str), \
                f"refresh_token should be str, got {type(result.refresh_token)}"
