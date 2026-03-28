from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from uuid import uuid4, UUID
import secrets

from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.db.database import get_db
from app.models.models import User, Organization, LocalAgent
from app.api import dependencies
from app.api.dependencies import get_current_user
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None
    role: str = "viewer"


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class AgentCreate(BaseModel):
    name: str
    site_id: str | None = None


class AgentResponse(BaseModel):
    agent_id: str
    organization_id: str
    name: str
    api_key: str
    message: str


@router.post("/login", response_model=TokenResponse)
async def login(credentials: UserLogin, db: AsyncSession = Depends(get_db)):
    """Login with email and password, returns access + refresh tokens"""
    result = await db.execute(select(User).where(User.email == credentials.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive"
        )

    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "org_id": str(user.organization_id),
            "role": user.role,
        }
    )
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    from app.api.schemas import User as UserSchema
    current_user = UserSchema(
        id=str(user.id),
        email=user.email,
        organization_id=str(user.organization_id),
        role=user.role,
        is_active=user.is_active,
    )
    await dependencies.audit_log(
        action="user.login",
        resource_type="user",
        resource_id=str(user.id),
        resource_name=user.email,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshTokenRequest, db: AsyncSession = Depends(get_db)
):
    """Refresh access token using refresh token"""
    try:
        payload = decode_token(request.refresh_token)
        user_id = payload.get("sub")

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
            )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "org_id": str(user.organization_id),
            "role": user.role,
        }
    )

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/agent/register", response_model=AgentResponse)
async def register_agent(
    agent_data: AgentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register a new agent for the organization"""
    api_key = f"ndi_agent_{secrets.token_urlsafe(32)}"

    org_id = UUID(current_user.organization_id)
    site_uuid = UUID(agent_data.site_id) if agent_data.site_id else None

    agent = LocalAgent(
        id=uuid4(),
        organization_id=org_id,
        site_id=site_uuid,
        name=agent_data.name,
        api_key_hash=hash_password(api_key),
        is_active=True,
        capabilities={},
    )

    db.add(agent)
    await db.commit()
    await db.refresh(agent)

    await dependencies.audit_log(
        action="user.register",
        resource_type="agent",
        resource_id=str(agent.id),
        resource_name=agent.name,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return AgentResponse(
        agent_id=str(agent.id),
        organization_id=str(agent.organization_id),
        name=agent.name,
        api_key=api_key,
        message="Save this API key - it won't be shown again",
    )


@router.post("/logout")
async def logout():
    """Logout endpoint - client should discard tokens"""
    return {"message": "Successfully logged out"}


@router.post(
    "/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED
)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    """Register a new user"""
    result = await db.execute(select(User).where(User.email == user_data.email))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )

    new_org = Organization(
        id=uuid4(),
        name=f"Organization for {user_data.email}",
        slug=f"org-{uuid4().hex[:8]}",
    )
    db.add(new_org)
    await db.flush()

    new_user = User(
        id=uuid4(),
        organization_id=new_org.id,
        email=user_data.email,
        hashed_password=hash_password(user_data.password),
        full_name=user_data.full_name,
        role=user_data.role,
        is_active=True,
    )

    db.add(new_user)
    await db.commit()

    await dependencies.audit_log(
        action="user.register",
        resource_type="user",
        resource_id=str(new_user.id),
        resource_name=new_user.email,
        outcome="success",
        db=db,
    )

    access_token = create_access_token(
        data={
            "sub": str(new_user.id),
            "org_id": str(new_user.organization_id),
            "role": new_user.role,
        }
    )
    refresh_token = create_refresh_token(data={"sub": str(new_user.id)})

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)
