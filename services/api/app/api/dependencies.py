"""
API Dependencies
"""

from uuid import UUID, uuid4
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Header, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.schemas import User
from services.api.app.core.config import settings
from services.api.app.core.security import decode_token
from services.api.app.models.models import AuditLog, LocalAgent, User as UserModel

from services.api.app.db.database import get_db


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
        is_active=user.is_active,
    )


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get current active user"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )
    return current_user


async def get_internal_api_key(x_internal_api_key: str = Header(...)) -> str:
    """Validate internal API key for service-to-service communication"""
    if x_internal_api_key != settings.INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid internal API key")
    return x_internal_api_key


async def get_agent_auth(
    x_agent_key: str = Header(..., alias="X-Agent-Key"),
    db: AsyncSession = Depends(get_db),
) -> "AgentAuth":
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

    from app.api.schemas import AgentAuth

    agent_context = None
    for agent in agents:
        if verify_password(x_agent_key, agent.api_key_hash):
            agent_context = AgentAuth(
                agent_id=str(agent.id),
                organization_id=str(agent.organization_id),
                agent_name=agent.name,
            )
            break

    if not agent_context:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid agent API key"
        )

    return agent_context


async def audit_log(
    action: str,
    resource_type: str,
    resource_id: str = None,
    resource_name: str = None,
    outcome: str = "success",
    details: dict = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Write an audit log entry for the current request.

    Args:
        action: The action performed (e.g., 'device.view', 'device.create')
        resource_type: The type of resource (e.g., 'device', 'site', 'credential')
        resource_id: The ID of the resource (optional)
        resource_name: The name of the resource (optional)
        outcome: 'success', 'failure', or 'denied'
        details: Additional details as a dict
    """
    if details is None:
        details = {}
    audit_entry = AuditLog(
        id=uuid4(),
        organization_id=UUID(current_user.organization_id),
        user_id=UUID(current_user.id),
        action=action,
        resource_type=resource_type,
        resource_id=UUID(resource_id) if resource_id else None,
        resource_name=resource_name,
        outcome=outcome,
        details=details,
        timestamp=datetime.now(timezone.utc),
    )

    db.add(audit_entry)
    await db.commit()

    return audit_entry
