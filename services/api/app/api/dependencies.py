"""
API Dependencies
"""

from fastapi import Depends, HTTPException, Header
from app.core.config import settings
from app.api.schemas import User


async def get_current_user(
    authorization: str = Header(None)
) -> User:
    """
    Get current authenticated user
    TODO: Implement JWT validation
    """
    # TODO: Validate JWT token and return user
    # For now, return a placeholder
    return User(
        id="placeholder-user-id",
        email="user@example.com",
        organization_id="placeholder-org-id",
        role="admin"
    )


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Get current active user"""
    # TODO: Check if user is active
    return current_user


async def get_internal_api_key(
    x_internal_api_key: str = Header(...)
) -> str:
    """Validate internal API key for service-to-service communication"""
    if x_internal_api_key != settings.INTERNAL_API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid internal API key"
        )
    return x_internal_api_key
