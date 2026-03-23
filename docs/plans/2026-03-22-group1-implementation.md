# Group 1 Implementation Plan — NetDiscoverIT Phase 2

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement three foundational features: rate limiting, IntegrationConfig CRUD endpoints, and WebSocket for real-time discovery status.

**Architecture:** 
- Rate limiting uses SlowAPI with Redis storage for distributed rate limiting
- IntegrationConfig CRUD follows existing patterns in routes.py with Fernet encryption for credentials
- WebSocket uses FastAPI native WebSocket with Redis pub/sub for cross-instance messaging

**Tech Stack:** FastAPI, SlowAPI, Redis, WebSocket, Fernet encryption

---

## Task 1: Rate Limiting (1a)

### Overview
Add rate limiting to protect API endpoints from abuse. Uses SlowAPI with Redis for distributed rate limiting.

### Files
- Modify: `services/api/requirements.txt`
- Modify: `services/api/app/main.py`
- Modify: `services/api/app/core/config.py`

### Step 1: Add slowapi to requirements.txt

**Step 1.1: Add dependency**

Run: `cd /home/openether/NetDiscoverIT/services/api && echo "slowapi==0.1.9" >> requirements.txt`

**Step 1.2: Add rate limit configuration**

Modify: `services/api/app/core/config.py`

Add after existing settings:
```python
RATE_LIMIT_ENABLED: bool = True
RATE_LIMIT_WRITE: str = "60/minute"
RATE_LIMIT_READ: str = "200/minute"
```

**Step 1.3: Add rate limiter to main.py**

Modify: `services/api/app/main.py`

Add after CORS middleware:
```python
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse

limiter = Limiter(key_func=get_remote_address)

app.state.limiter = limiter

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request, exc):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded"}
    )
```

**Step 1.4: Apply rate limits to routes**

Modify: `services/api/app/api/routes.py`

Add to write endpoints (POST, PATCH, DELETE):
```python
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)

# Add to create_device, update_device, delete_device, trigger_discovery, etc.
@router.post("/devices", response_model=schemas.Device, status_code=201)
@limiter.limit("60/minute")
async def create_device(...):
```

Add to read endpoints (GET):
```python
@router.get("/devices", response_model=List[schemas.Device])
@limiter.limit("200/minute")
async def list_devices(...):
```

---

## Task 2: IntegrationConfig CRUD Endpoints (1b)

### Overview
Implement full CRUD for IntegrationConfig with Fernet-encrypted credentials storage.

### Files
- Modify: `services/api/app/api/routes.py`
- Modify: `services/api/app/api/schemas.py`

### Step 1: Add IntegrationConfig schemas

Modify: `services/api/app/api/schemas.py`

Add after IntegrationConfigResponse:
```python
class IntegrationConfigUpdate(BaseModel):
    """Integration config update request"""
    name: str | None = None
    base_url: str | None = None
    config: dict | None = None
    credentials: dict | None = None
    webhook_secret: str | None = None
    is_enabled: bool | None = None


class IntegrationConfigTestRequest(BaseModel):
    """Request to test an integration"""
    test_message: str | None = "Test message from NetDiscoverIT"


class IntegrationConfigTestResponse(BaseModel):
    """Response from integration test"""
    success: bool
    message: str
    details: dict | None = None
```

### Step 2: Add IntegrationConfig CRUD routes

Modify: `services/api/app/api/routes.py`

Add after alert events routes (line ~1473):
```python
# =============================================================================
# INTEGRATION CONFIGS
# =============================================================================
@router.get("/integrations", response_model=List[schemas.IntegrationConfigResponse])
async def list_integrations(
    skip: int = 0,
    limit: int = 100,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all integrations for user's organization"""
    from uuid import UUID
    from sqlalchemy import select
    from app.models.models import IntegrationConfig

    org_id = UUID(current_user.organization_id)
    result = await db.execute(
        select(IntegrationConfig)
        .where(IntegrationConfig.organization_id == org_id)
        .offset(skip)
        .limit(limit)
    )
    integrations = result.scalars().all()

    await dependencies.audit_log(
        action="integration_config.list",
        resource_type="integration_config",
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return [
        schemas.IntegrationConfigResponse(
            id=str(i.id),
            organization_id=str(i.organization_id),
            integration_type=i.integration_type,
            name=i.name,
            base_url=i.base_url,
            config=i.config or {},
            is_enabled=i.is_enabled,
            created_at=i.created_at,
            updated_at=i.updated_at,
        )
        for i in integrations
    ]


@router.get("/integrations/{integration_id}", response_model=schemas.IntegrationConfigResponse)
async def get_integration(
    integration_id: str,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific integration config"""
    from uuid import UUID
    from sqlalchemy import select
    from app.models.models import IntegrationConfig

    try:
        integration_uuid = UUID(integration_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid integration ID format")

    result = await db.execute(
        select(IntegrationConfig).where(
            IntegrationConfig.id == integration_uuid,
            IntegrationConfig.organization_id == UUID(current_user.organization_id),
        )
    )
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    await dependencies.audit_log(
        action="integration_config.view",
        resource_type="integration_config",
        resource_id=integration_id,
        resource_name=integration.name,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return schemas.IntegrationConfigResponse(
        id=str(integration.id),
        organization_id=str(integration.organization_id),
        integration_type=integration.integration_type,
        name=integration.name,
        base_url=integration.base_url,
        config=integration.config or {},
        is_enabled=integration.is_enabled,
        created_at=integration.created_at,
        updated_at=integration.updated_at,
    )


@router.post("/integrations", response_model=schemas.IntegrationConfigResponse, status_code=201)
async def create_integration(
    integration: schemas.IntegrationConfigCreate,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new integration config"""
    from uuid import UUID, uuid4
    from sqlalchemy import select
    from app.models.models import IntegrationConfig
    import json

    org_id = UUID(current_user.organization_id)

    # Check for duplicate name
    result = await db.execute(
        select(IntegrationConfig).where(
            IntegrationConfig.organization_id == org_id,
            IntegrationConfig.name == integration.name,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Integration with this name already exists")

    # Encrypt credentials
    credentials_json = json.dumps(integration.credentials)
    encrypted_creds = None
    if integration.credentials:
        from cryptography.fernet import Fernet
        from app.core.config import settings
        fernet = Fernet(settings.CREDENTIAL_ENCRYPTION_KEY.encode())
        encrypted_creds = fernet.encrypt(credentials_json.encode()).decode()

    # Encrypt webhook secret
    encrypted_webhook_secret = None
    if integration.webhook_secret:
        from cryptography.fernet import Fernet
        from app.core.config import settings
        fernet = Fernet(settings.CREDENTIAL_ENCRYPTION_KEY.encode())
        encrypted_webhook_secret = fernet.encrypt(integration.webhook_secret.encode()).decode()

    integration_obj = IntegrationConfig(
        id=uuid4(),
        organization_id=org_id,
        integration_type=integration.integration_type.value,
        name=integration.name,
        base_url=integration.base_url,
        config=integration.config,
        encrypted_credentials=encrypted_creds,
        webhook_secret=encrypted_webhook_secret,
        is_enabled=True,
    )

    db.add(integration_obj)
    await db.commit()
    await db.refresh(integration_obj)

    await dependencies.audit_log(
        action="integration_config.create",
        resource_type="integration_config",
        resource_id=str(integration_obj.id),
        resource_name=integration_obj.name,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return schemas.IntegrationConfigResponse(
        id=str(integration_obj.id),
        organization_id=str(integration_obj.organization_id),
        integration_type=integration_obj.integration_type,
        name=integration_obj.name,
        base_url=integration_obj.base_url,
        config=integration_obj.config or {},
        is_enabled=integration_obj.is_enabled,
        created_at=integration_obj.created_at,
        updated_at=integration_obj.updated_at,
    )


@router.patch("/integrations/{integration_id}", response_model=schemas.IntegrationConfigResponse)
async def update_integration(
    integration_id: str,
    integration_update: schemas.IntegrationConfigUpdate,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an integration config"""
    from uuid import UUID
    from sqlalchemy import select
    from app.models.models import IntegrationConfig
    import json

    try:
        integration_uuid = UUID(integration_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid integration ID format")

    result = await db.execute(
        select(IntegrationConfig).where(
            IntegrationConfig.id == integration_uuid,
            IntegrationConfig.organization_id == UUID(current_user.organization_id),
        )
    )
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    update_data = integration_update.model_dump(exclude_unset=True)

    # Handle credential encryption if provided
    if "credentials" in update_data and update_data["credentials"]:
        from cryptography.fernet import Fernet
        from app.core.config import settings
        fernet = Fernet(settings.CREDENTIAL_ENCRYPTION_KEY.encode())
        credentials_json = json.dumps(update_data["credentials"])
        integration.encrypted_credentials = fernet.encrypt(credentials_json.encode()).decode()
        del update_data["credentials"]

    # Handle webhook secret encryption if provided
    if "webhook_secret" in update_data and update_data["webhook_secret"]:
        from cryptography.fernet import Fernet
        from app.core.config import settings
        fernet = Fernet(settings.CREDENTIAL_ENCRYPTION_KEY.encode())
        integration.webhook_secret = fernet.encrypt(update_data["webhook_secret"].encode()).decode()
        del update_data["webhook_secret"]

    for field, value in update_data.items():
        if value is not None:
            setattr(integration, field, value)

    await db.commit()
    await db.refresh(integration)

    await dependencies.audit_log(
        action="integration_config.update",
        resource_type="integration_config",
        resource_id=integration_id,
        resource_name=integration.name,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return schemas.IntegrationConfigResponse(
        id=str(integration.id),
        organization_id=str(integration.organization_id),
        integration_type=integration.integration_type,
        name=integration.name,
        base_url=integration.base_url,
        config=integration.config or {},
        is_enabled=integration.is_enabled,
        created_at=integration.created_at,
        updated_at=integration.updated_at,
    )


@router.delete("/integrations/{integration_id}", status_code=204)
async def delete_integration(
    integration_id: str,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an integration config"""
    from uuid import UUID
    from sqlalchemy import select
    from app.models.models import IntegrationConfig

    try:
        integration_uuid = UUID(integration_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid integration ID format")

    result = await db.execute(
        select(IntegrationConfig).where(
            IntegrationConfig.id == integration_uuid,
            IntegrationConfig.organization_id == UUID(current_user.organization_id),
        )
    )
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    await db.delete(integration)
    await db.commit()

    await dependencies.audit_log(
        action="integration_config.delete",
        resource_type="integration_config",
        resource_id=integration_id,
        resource_name=integration.name,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return None


@router.post("/integrations/{integration_id}/test", response_model=schemas.IntegrationConfigTestResponse)
async def test_integration(
    integration_id: str,
    test_request: schemas.IntegrationConfigTestRequest,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Test an integration configuration"""
    from uuid import UUID
    from sqlalchemy import select
    from app.models.models import IntegrationConfig
    import json

    try:
        integration_uuid = UUID(integration_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid integration ID format")

    result = await db.execute(
        select(IntegrationConfig).where(
            IntegrationConfig.id == integration_uuid,
            IntegrationConfig.organization_id == UUID(current_user.organization_id),
        )
    )
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    # Decrypt credentials for testing
    credentials = None
    if integration.encrypted_credentials:
        from cryptography.fernet import Fernet
        from app.core.config import settings
        fernet = Fernet(settings.CREDENTIAL_ENCRYPTION_KEY.encode())
        try:
            creds_decrypted = fernet.decrypt(integration.encrypted_credentials.encode()).decode()
            credentials = json.loads(creds_decrypted)
        except Exception as e:
            return schemas.IntegrationConfigTestResponse(
                success=False,
                message="Failed to decrypt credentials",
                details={"error": str(e)},
            )

    # Test based on integration type
    test_result = await _test_integration(integration, credentials, test_request.test_message)

    await dependencies.audit_log(
        action="integration_config.test",
        resource_type="integration_config",
        resource_id=integration_id,
        resource_name=integration.name,
        outcome="success" if test_result["success"] else "failure",
        current_user=current_user,
        db=db,
    )

    return schemas.IntegrationConfigTestResponse(
        success=test_result["success"],
        message=test_result["message"],
        details=test_result.get("details"),
    )


async def _test_integration(integration, credentials, test_message):
    """Test integration connectivity based on type"""
    import httpx

    integration_type = integration.integration_type
    base_url = integration.base_url

    try:
        if integration_type == "slack":
            # Test Slack webhook
            if not credentials or "webhook_url" not in credentials:
                return {"success": False, "message": "Missing webhook_url in credentials"}
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    credentials["webhook_url"],
                    json={"text": test_message or "Test message from NetDiscoverIT"},
                    timeout=10,
                )
                if response.status_code == 200:
                    return {"success": True, "message": "Slack webhook test successful"}
                return {"success": False, "message": f"Slack webhook failed: {response.status_code}"}

        elif integration_type == "teams":
            # Test Teams webhook
            if not credentials or "webhook_url" not in credentials:
                return {"success": False, "message": "Missing webhook_url in credentials"}
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    credentials["webhook_url"],
                    json={"text": test_message or "Test message from NetDiscoverIT"},
                    timeout=10,
                )
                if response.status_code == 200:
                    return {"success": True, "message": "Teams webhook test successful"}
                return {"success": False, "message": f"Teams webhook failed: {response.status_code}"}

        elif integration_type == "servicenow":
            # Test ServiceNow API
            if not credentials or not base_url:
                return {"success": False, "message": "Missing credentials or base_url"}
            
            async with httpx.AsyncClient() as client:
                auth = (credentials.get("username", ""), credentials.get("password", ""))
                response = await client.get(
                    f"{base_url}/api/now/table/change_request",
                    auth=auth,
                    params={"sysparm_limit": 1},
                    timeout=10,
                )
                if response.status_code == 200:
                    return {"success": True, "message": "ServiceNow API test successful"}
                return {"success": False, "message": f"ServiceNow API failed: {response.status_code}"}

        elif integration_type == "jira":
            # Test JIRA API
            if not credentials or not base_url:
                return {"success": False, "message": "Missing credentials or base_url"}
            
            async with httpx.AsyncClient() as client:
                headers = {
                    "Authorization": f"Basic {credentials.get('api_token', '')}",
                    "Content-Type": "application/json",
                }
                response = await client.get(
                    f"{base_url}/rest/api/3/myself",
                    headers=headers,
                    timeout=10,
                )
                if response.status_code == 200:
                    return {"success": True, "message": "JIRA API test successful"}
                return {"success": False, "message": f"JIRA API failed: {response.status_code}"}

        elif integration_type == "pagerduty":
            # Test PagerDuty Events API
            if not credentials or "routing_key" not in credentials:
                return {"success": False, "message": "Missing routing_key in credentials"}
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://events.pagerduty.net/v2/enqueue",
                    json={
                        "routing_key": credentials["routing_key"],
                        "event_action": "trigger",
                        "payload": {
                            "summary": test_message or "Test from NetDiscoverIT",
                            "severity": "info",
                        },
                    },
                    timeout=10,
                )
                if response.status_code in (200, 202):
                    return {"success": True, "message": "PagerDuty test successful"}
                return {"success": False, "message": f"PagerDuty failed: {response.status_code}"}

        else:
            return {"success": False, "message": f"Unsupported integration type: {integration_type}"}

    except Exception as e:
        return {"success": False, "message": f"Test failed: {str(e)}"}
```

---

## Task 3: WebSocket — Real-Time Discovery Status (1c)

### Overview
Add WebSocket support for real-time discovery progress updates. Uses Redis pub/sub for cross-instance messaging.

### Files
- Modify: `services/api/requirements.txt`
- Modify: `services/api/app/main.py`
- Create: `services/api/app/api/websocket.py`
- Modify: `services/api/app/api/routes.py`

### Step 1: Add websocket dependencies

Run: `cd /home/openether/NetDiscoverIT/services/api && echo "websockets>=12.0" >> requirements.txt`

### Step 2: Create WebSocket manager

Create: `services/api/app/api/websocket.py`

```python
"""
WebSocket manager for real-time updates
"""
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List
import json
import redis
from app.core.config import settings


class ConnectionManager:
    """Manages WebSocket connections"""

    def __init__(self):
        # active_connections: {discovery_id: [WebSocket]}
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, discovery_id: str):
        """Connect a WebSocket to a discovery room"""
        await websocket.accept()
        if discovery_id not in self.active_connections:
            self.active_connections[discovery_id] = []
        self.active_connections[discovery_id].append(websocket)

    def disconnect(self, websocket: WebSocket, discovery_id: str):
        """Disconnect a WebSocket from a discovery room"""
        if discovery_id in self.active_connections:
            if websocket in self.active_connections[discovery_id]:
                self.active_connections[discovery_id].remove(websocket)
            if not self.active_connections[discovery_id]:
                del self.active_connections[discovery_id]

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Send a message to a specific WebSocket"""
        await websocket.send_json(message)

    async def broadcast_to_discovery(self, discovery_id: str, message: dict):
        """Broadcast a message to all WebSockets subscribed to a discovery"""
        if discovery_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[discovery_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    disconnected.append(connection)
            # Clean up disconnected clients
            for conn in disconnected:
                self.disconnect(conn, discovery_id)


manager = ConnectionManager()


async def publish_discovery_update(discovery_id: str, update: dict):
    """Publish a discovery update to Redis pub/sub"""
    try:
        redis_client = redis.from_url(settings.REDIS_URL)
        channel = f"discovery:{discovery_id}:updates"
        redis_client.publish(channel, json.dumps(update))
        redis_client.close()
    except Exception as e:
        import logging
        logging.warning(f"Failed to publish discovery update: {e}")


async def subscribe_to_discovery_updates(discovery_id: str):
    """Subscribe to Redis pub/sub for discovery updates"""
    try:
        redis_client = redis.from_url(settings.REDIS_URL)
        pubsub = redis_client.pubsub()
        channel = f"discovery:{discovery_id}:updates"
        pubsub.subscribe(channel)
        
        for message in pubsub.listen():
            if message["type"] == "message":
                yield json.loads(message["data"])
    except Exception as e:
        import logging
        logging.warning(f"Failed to subscribe to discovery updates: {e}")
```

### Step 3: Add WebSocket route

Modify: `services/api/app/api/routes.py`

Add at the top of the file:
```python
from app.api.websocket import manager
```

Add after health endpoint:
```python
@router.websocket("/ws/discoveries/{discovery_id}")
async def websocket_discovery_status(websocket: WebSocket, discovery_id: str):
    """
    WebSocket endpoint for real-time discovery status updates.
    
    Frontend connects to: ws://localhost:8000/api/v1/ws/discoveries/{discovery_id}
    
    Messages received:
    - {"type": "progress", "progress": 50, "status": "running", "message": "Scanning..."}
    - {"type": "complete", "device_count": 42}
    - {"type": "error", "message": "Scan failed"}
    """
    await manager.connect(websocket, discovery_id)
    try:
        while True:
            # Keep connection alive, wait for messages from Redis pub/sub
            data = await websocket.receive_text()
            # Echo back for ping/pong keepalive
            await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        manager.disconnect(websocket, discovery_id)
```

### Step 4: Update discovery to publish progress

Modify: `services/api/app/api/routes.py`

In `trigger_discovery` function, add Redis publish after status update:

```python
# After updating discovery status to running
from app.api.websocket import publish_discovery_update
await publish_discovery_update(
    str(discovery_id),
    {"type": "progress", "progress": 0, "status": "running", "message": "Discovery started"}
)
```

---

## Testing Commands

```bash
# Start services
cd /home/openether/NetDiscoverIT && make up

# Test rate limiting
for i in {1..65}; do curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/v1/devices; done

# Test WebSocket (requires frontend integration)
# Connect to: ws://localhost:8000/api/v1/ws/discoveries/{discovery_id}

# Test integrations CRUD
curl -X POST http://localhost:8000/api/v1/integrations \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "integration_type": "slack",
    "name": "Test Slack",
    "config": {"channel_id": "C123"},
    "credentials": {"webhook_url": "https://hooks.slack.com/test"}
  }'
```

---

## Dependencies Added

- `slowapi==0.1.9` - Rate limiting
- `websockets>=12.0` - WebSocket support

---

## Estimated Effort

- Task 1a (Rate Limiting): ~2 hours
- Task 1b (IntegrationConfig CRUD): ~4 hours  
- Task 1c (WebSocket): ~4 hours

**Total: ~10 hours**
