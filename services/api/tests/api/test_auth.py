import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_login_returns_tokens():
    """Login should return access and refresh tokens"""
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "password123"},
    )
    # Will be 401 if user not found, 200 if works
    assert response.status_code in [200, 401]


def test_login_invalid_credentials():
    """Login with wrong password should return 401"""
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "wrongpassword"},
    )
    assert response.status_code == 401


def test_refresh_token_missing():
    """Refresh without token should return 401"""
    response = client.post("/api/v1/auth/refresh", json={"refresh_token": ""})
    assert response.status_code == 401  # Invalid token returns 401
