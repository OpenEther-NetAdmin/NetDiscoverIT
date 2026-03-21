import pytest
from datetime import timedelta
from app.core.security import verify_password, hash_password, create_access_token, decode_token


def test_hash_and_verify_password():
    password = "SecurePass123!"
    hashed = hash_password(password)
    
    assert verify_password(password, hashed) is True
    assert verify_password("wrongpassword", hashed) is False


def test_create_and_decode_access_token():
    token = create_access_token(
        data={"sub": "user-123", "org_id": "org-456", "role": "admin"},
        expires_delta=timedelta(minutes=15)
    )
    
    payload = decode_token(token)
    assert payload["sub"] == "user-123"
    assert payload["org_id"] == "org-456"
    assert payload["role"] == "admin"


def test_decode_invalid_token_raises():
    with pytest.raises(Exception):
        decode_token("invalid.token.here")
