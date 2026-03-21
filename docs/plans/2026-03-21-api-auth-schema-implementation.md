# API Authentication & Schema Expansion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement JWT authentication (access + refresh tokens), agent API key auth, and expand Pydantic schemas for users, credentials, and integrations.

**Architecture:** Full JWT with access (15min) and refresh (7d) tokens using python-jose. Agent API key uses bcrypt hash verification against LocalAgent table. Schemas expand user management, credentials, and integration configs.

**Tech Stack:** Python 3.11, FastAPI, python-jose, passlib[bcrypt], pytest

---

## Phase 1: Security Module & JWT Core

### Task 1: Create security module with password hashing and token utilities

**Files:**
- Create: `services/api/app/core/security.py`
- Test: `services/api/tests/core/test_security.py`

**Step 1: Write the failing test**

```python
# services/api/tests/core/test_security.py
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
```

**Step 2: Run test to verify it fails**

```bash
cd /home/openether/NetDiscoverIT/services/api
pytest tests/core/test_security.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.core.security'`

**Step 3: Write minimal implementation**

```python
# services/api/app/core/security.py
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash"""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """Create a JWT refresh token (7 days)"""
    return create_access_token(
        data=data,
        expires_delta=timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    )


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token"""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError as e:
        raise ValueError(f"Invalid token: {e}")
```

**Step 4: Run test to verify it passes**

```bash
cd /home/openether/NetDiscoverIT/services/api
pytest tests/core/test_security.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add tests/core/test_security.py app/core/security.py
git commit -m "feat(auth): Add security module with password hashing and JWT utilities"
```

---

### Task 2: Add python-jose and passlib to dependencies

**Step 1: Check requirements.txt**

```bash
cd /home/openether/NetDiscoverIT/services/api
cat requirements.txt
```

**Step 2: Add missing dependencies**

```bash
echo "python-jose[cryptography]>=3.3.0" >> requirements.txt
echo "passlib[bcrypt]>=1.7.4" >> requirements.txt
```

**Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add python-jose and passlib dependencies"
```

---

## Phase 2: JWT Authentication Endpoints

### Task 3: Create auth routes

**Files:**
- Create: `services/api/app/api/auth.py`
- Test: `services/api/tests/api/test_auth.py`

**Step 1: Write the failing test**

```python
# services/api/tests/api/test_auth.py
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_login_returns_tokens():
    # This will fail because we haven't implemented login yet
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "password123"}
    )
    assert response.status_code in [200, 401]  # 401 if user not found


def test_login_invalid_credentials():
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "wrongpassword"}
    )
    assert response.status_code == 401


def test_refresh_token_missing():
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 401
```

**Step 2: Run test to verify it fails**

```bash
cd /home/openether/NetDiscoverIT/services/api
pytest tests/api/test_auth.py -v
```

Expected: `404 Not Found` for `/api/v1/auth/login`

**Step 3: Write auth routes implementation**

```python
# services/api/app/api/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from datetime import timedelta

from app.core.security import (
    hash_password, verify_password, create_access_token, 
    create_refresh_token, decode_token
)
from app.core.config import settings
from app.api.dependencies import get_db
from app.models.models import User
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


@router.post("/login", response_model=TokenResponse)
async def login(
    credentials: UserLogin,
    db: AsyncSession = Depends(get_db)
):
    """Login with email and password, returns access + refresh tokens"""
    # Find user by email
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
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )
    
    # Create tokens
    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "org_id": str(user.organization_id),
            "role": user.role
        }
    )
    refresh_token = create_refresh_token(
        data={"sub": str(user.id)}
    )
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db)
):
    """Refresh access token using refresh token"""
    try:
        payload = decode_token(request.refresh_token)
        user_id = payload.get("sub")
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )
    
    # Get user
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
    
    # Create new tokens (refresh token rotation)
    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "org_id": str(user.organization_id),
            "role": user.role
        }
    )
    new_refresh_token = create_refresh_token(
        data={"sub": str(user.id)}
    )
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token
    )


@router.post("/logout")
async def logout():
    """Logout endpoint - client should discard tokens"""
    # In a full implementation, we'd blacklist the refresh token
    # For now, client-side logout is sufficient
    return {"message": "Successfully logged out"}


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    """Register a new user (for initial setup or invite-based)"""
    # Check if email exists
    result = await db.execute(select(User).where(User.email == user_data.email))
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create user with hashed password
    # Note: In production, you'd need organization_id from context
    # For now, create a placeholder
    from uuid import uuid4
    new_user = User(
        id=uuid4(),
        organization_id=uuid4(),  # Would come from invite/context
        email=user_data.email,
        hashed_password=hash_password(user_data.password),
        full_name=user_data.full_name,
        role=user_data.role,
        is_active=True
    )
    
    db.add(new_user)
    await db.commit()
    
    # Create tokens
    access_token = create_access_token(
        data={
            "sub": str(new_user.id),
            "org_id": str(new_user.organization_id),
            "role": new_user.role
        }
    )
    refresh_token = create_refresh_token(
        data={"sub": str(new_user.id)}
    )
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token
    )
```

**Step 4: Register auth router in main.py**

```python
# services/api/app/main.py - add this import and router
from app.api.auth import router as auth_router

app.include_router(auth_router, prefix="/api/v1")
```

**Step 5: Run test to verify it passes**

```bash
cd /home/openether/NetDiscoverIT/services/api
pytest tests/api/test_auth.py -v
```

**Step 6: Commit**

```bash
git add app/api/auth.py app/main.py tests/api/test_auth.py
git commit -m "feat(auth): Add JWT authentication endpoints (login, refresh, logout, register)"
```

---

### Task 4: Update get_current_user dependency to validate JWT

**Files:**
- Modify: `services/api/app/api/dependencies.py:10-24`

**Step 1: Read current dependencies.py**

```bash
cat /home/openether/NetDiscoverIT/services/api/app/api/dependencies.py
```

**Step 2: Update get_current_user**

```python
# Replace the existing get_current_user function

async def get_current_user(
    authorization: str = Header(None),
    db: AsyncSession = Depends(get_db)
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
        from app.core.security import decode_token
        payload = decode_token(token)
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except Exception:
        raise credentials_exception
    
    # Get user from database
    from uuid import UUID
    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    
    if user is None:
        raise credentials_exception
    
    return User(
        id=str(user.id),
        email=user.email,
        organization_id=str(user.organization_id),
        role=user.role
    )
```

**Step 3: Commit**

```bash
git add app/api/dependencies.py
git commit -m "feat(auth): Update get_current_user to validate JWT tokens"
```

---

## Phase 3: Agent API Key Authentication

### Task 5: Add agent authentication dependency

**Files:**
- Modify: `services/api/app/api/dependencies.py`

**Step 1: Add get_agent_auth dependency**

```python
# Add after get_internal_api_key function

async def get_agent_auth(
    x_agent_key: str = Header(..., alias="X-Agent-Key"),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Validate agent API key from X-Agent-Key header.
    Returns agent context with org_id and agent_id.
    """
    if not x_agent_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Agent-Key header"
        )
    
    # Find agent by plaintext key (need to check hash)
    # Note: In production, you'd use a faster lookup with prefix or index
    from app.core.security import verify_password
    from uuid import UUID
    
    result = await db.execute(select(LocalAgent).where(LocalAgent.is_active == True))
    agents = result.scalars().all()
    
    agent_context = None
    for agent in agents:
        if verify_password(x_agent_key, agent.api_key_hash):
            agent_context = {
                "agent_id": str(agent.id),
                "organization_id": str(agent.organization_id),
                "agent_name": agent.name
            }
            break
    
    if not agent_context:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid agent API key"
        )
    
    return agent_context
```

**Step 2: Import LocalAgent model**

```python
# Add to imports at top
from app.models.models import LocalAgent
```

**Step 3: Commit**

```bash
git add app/api/dependencies.py
git commit -m "feat(auth): Add agent API key authentication dependency"
```

---

### Task 6: Add agent registration endpoint

**Files:**
- Modify: `services/api/app/api/auth.py`

**Step 1: Add agent registration endpoint**

```python
# Add to auth.py after /register endpoint

class AgentCreate(BaseModel):
    name: str
    site_id: str | None = None


class AgentResponse(BaseModel):
    agent_id: str
    organization_id: str
    name: str
    api_key: str  # Only returned once!
    message: str


@router.post("/agent/register", response_model=AgentResponse)
async def register_agent(
    agent_data: AgentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Register a new agent for the organization"""
    from uuid import uuid4
    from app.core.security import hash_password, hash_password  # For API key
    
    # Generate a secure API key
    import secrets
    api_key = f"ndi_agent_{secrets.token_urlsafe(32)}"
    
    # Get organization_id from current user
    org_id = UUID(current_user.organization_id)
    site_uuid = UUID(agent_data.site_id) if agent_data.site_id else None
    
    agent = LocalAgent(
        id=uuid4(),
        organization_id=org_id,
        site_id=site_uuid,
        name=agent_data.name,
        api_key_hash=hash_password(api_key),
        is_active=True,
        capabilities={}
    )
    
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    
    return AgentResponse(
        agent_id=str(agent.id),
        organization_id=str(agent.organization_id),
        name=agent.name,
        api_key=api_key,  # Only returned now!
        message="Save this API key - it won't be shown again"
    )
```

**Step 2: Import LocalAgent**

```python
# Add to imports
from app.models.models import LocalAgent
```

**Step 3: Commit**

```bash
git add app/api/auth.py
git commit -m "feat(auth): Add agent registration endpoint"
```

---

## Phase 4: Expand Pydantic Schemas

### Task 7: Expand user schemas

**Files:**
- Modify: `services/api/app/api/schemas.py`

**Step 1: Add expanded user schemas**

```python
# Add these schemas after existing User schema

class UserLogin(BaseModel):
    """User login request"""
    email: EmailStr
    password: str


class UserCreate(BaseModel):
    """User creation request"""
    email: EmailStr
    password: str  # Will be hashed
    full_name: str | None = None
    role: str = "viewer"


class UserUpdate(BaseModel):
    """User update request"""
    email: EmailStr | None = None
    full_name: str | None = None
    role: str | None = None
    password: str | None = None  # If provided, will be hashed
    is_active: bool | None = None


class UserResponse(BaseModel):
    """User response (excludes sensitive fields)"""
    id: str
    email: str
    organization_id: str
    full_name: str | None = None
    role: str
    is_active: bool
    last_login: datetime | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    """JWT token response"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
```

**Step 2: Commit**

```bash
git add app/api/schemas.py
git commit -m "feat(schemas): Expand user schemas with login, create, update, response"
```

---

### Task 8: Add credential schemas

**Files:**
- Modify: `services/api/app/api/schemas.py`

**Step 1: Add credential schemas**

```python
# Add after DeviceMetadata

class CredentialType(str, Enum):
    """Credential types"""
    PASSWORD = "password"
    SSH_KEY = "ssh_key"
    API_TOKEN = "api_token"
    SNMP_COMMUNITY = "snmp_community"


class CredentialBase(BaseModel):
    """Base credential schema"""
    name: str
    username: str
    credential_type: CredentialType
    target_filter: dict = {}
    metadata: dict = {}


class CredentialCreate(CredentialBase):
    """Credential creation request (includes password)"""
    password: str  # Will be encrypted


class CredentialResponse(CredentialBase):
    """Credential response (excludes encrypted_password)"""
    id: str
    organization_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
```

**Step 2: Commit**

```bash
git add app/api/schemas.py
git commit -m "feat(schemas): Add credential schemas"
```

---

### Task 9: Add integration config schemas

**Files:**
- Modify: `services/api/app/api/schemas.py`

**Step 1: Add integration schemas**

```python
# Add after CredentialResponse

class IntegrationType(str, Enum):
    """Integration types"""
    SERVICENOW = "servicenow"
    JIRA = "jira"
    SLACK = "slack"
    TEAMS = "teams"
    PAGERDUTY = "pagerduty"
    OPSGENIE = "opsgenie"
    GITHUB = "github"
    ZENDESK = "zendesk"


class IntegrationConfigBase(BaseModel):
    """Base integration config schema"""
    integration_type: IntegrationType
    name: str
    base_url: str | None = None
    config: dict = {}


class IntegrationConfigCreate(IntegrationConfigBase):
    """Integration config creation (includes credentials)"""
    credentials: dict  # Will be encrypted
    webhook_secret: str | None = None


class IntegrationConfigResponse(IntegrationConfigBase):
    """Integration config response (excludes secrets)"""
    id: str
    organization_id: str
    is_enabled: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
```

**Step 2: Commit**

```bash
git add app/api/schemas.py
git commit -m "feat(schemas): Add integration config schemas"
```

---

## Phase 5: Update Routes with Auth

### Task 10: Update existing routes with proper auth dependencies

**Files:**
- Modify: `services/api/app/api/routes.py`

**Step 1: Update import and remove placeholder user**

```python
# Remove the placeholder user from get_current_user
# The dependency now validates real JWT

# Update routes to use proper auth
@router.get("/devices", response_model=List[schemas.Device])
async def list_devices(
    skip: int = 0,
    limit: int = 100,
    organization_id: Optional[str] = None,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(dependencies.get_db),
):
    """List all devices for user's organization"""
    from sqlalchemy import select
    from uuid import UUID
    
    # Filter by user's organization
    org_id = UUID(current_user.organization_id)
    result = await db.execute(
        select(Device)
        .where(Device.organization_id == org_id)
        .offset(skip)
        .limit(limit)
    )
    devices = result.scalars().all()
    
    return [
        schemas.Device(
            id=str(d.id),
            hostname=d.hostname,
            management_ip=str(d.ip_address),
            vendor=d.vendor,
            device_type=d.device_type,
            role=d.device_role,
            organization_id=str(d.organization_id),
            created_at=d.created_at,
            updated_at=d.updated_at
        )
        for d in devices
    ]
```

**Step 2: Update get_db dependency**

Add get_db to dependencies.py:

```python
async def get_db():
    """Database session dependency"""
    from app.db.database import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        yield session
```

**Step 3: Commit**

```bash
git add app/api/routes.py app/api/dependencies.py
git commit -m "feat(routes): Update routes with proper auth and database queries"
```

---

## Phase 6: Testing & Validation

### Task 11: Run full test suite

**Step 1: Run all tests**

```bash
cd /home/openether/NetDiscoverIT/services/api
pytest tests/ -v --tb=short
```

**Step 2: Run linting**

```bash
cd /home/openether/NetDiscoverIT
make lint
# or manually
flake8 services/api --max-line-length=120 --ignore=E501,W503
black --check services/api
```

**Step 3: Commit any fixes**

```bash
git add -A
git commit -m "fix: address lint and test issues"
```

---

## Summary

This implementation plan adds:

1. **JWT Authentication**
   - `/auth/login` - email/password → access + refresh tokens
   - `/auth/refresh` - rotate tokens
   - `/auth/logout` - client-side logout
   - `/auth/register` - user registration
   - Updated `get_current_user` dependency

2. **Agent API Key Auth**
   - `/auth/agent/register` - create agent, get API key
   - `get_agent_auth` dependency for agent routes

3. **Expanded Schemas**
   - User: UserLogin, UserCreate, UserUpdate, UserResponse, TokenResponse
   - Credential: CredentialCreate, CredentialResponse, CredentialType
   - Integration: IntegrationConfigCreate, IntegrationConfigResponse, IntegrationType

4. **Updated Routes**
   - All routes now properly validate JWT
   - Device listing filters by user's organization
