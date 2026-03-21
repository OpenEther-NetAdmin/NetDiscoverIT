"""
API Dependencies
"""

from uuid import UUID

from fastapi import Depends, HTTPException, Header, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import User
from app.core.config import settings
from app.core.security import decode_token
from app.models.models import LocalAgent, User as UserModel

from app.db.database import get_db


async def get_current_user(
    authorization: str = Header(None), db: AsyncSession = Depends(get_db)
) -> User:
    """
    Get current authenticated user from JWT access token.
    Requires Bearer token in Authorization header.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not authorization:
        raise credentials_exception

    # Extract token from "Bearer <token>"
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise credentials_exception
    except ValueError:
        raise credentials_exception

    # Decode token
    try:
        payload = decode_token(token)
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except Exception:
        raise credentials_exception

    # Get user from database
    result = await db.execute(select(UserModel).where(UserModel.id == UUID(user_id)))
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    return User(
        id=str(user.id),
        email=user.email,
        organization_id=str(user.organization_id),
        role=user.role,
    )


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get current active user"""
    # TODO: Check if user is active
    return current_user


async def get_internal_api_key(x_internal_api_key: str = Header(...)) -> str:
    """Validate internal API key for service-to-service communication"""
    if x_internal_api_key != settings.INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid internal API key")
    return x_internal_api_key


async def get_agent_auth(
    x_agent_key: str = Header(..., alias="X-Agent-Key"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Validate agent API key from X-Agent-Key header.
    Returns agent context with org_id and agent_id.
    """
    if not x_agent_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Agent-Key header",
        )

    from app.core.security import verify_password

    result = await db.execute(select(LocalAgent).where(LocalAgent.is_active is True))
    agents = result.scalars().all()

    agent_context = None
    for agent in agents:
        if verify_password(x_agent_key, agent.api_key_hash):
            agent_context = {
                "agent_id": str(agent.id),
                "organization_id": str(agent.organization_id),
                "agent_name": agent.name,
            }
            break

    if not agent_context:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid agent API key"
        )

    return agent_context
