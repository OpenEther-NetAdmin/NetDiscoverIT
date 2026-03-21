"""
API Routes
"""

from uuid import UUID
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import schemas
from app.api import dependencies
from app.api.dependencies import get_db, get_current_user, get_agent_auth
from app.models.models import Device, Site, LocalAgent

router = APIRouter()


# =============================================================================
# HEALTH
# =============================================================================
@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


# =============================================================================
# DEVICES
# =============================================================================
@router.get("/devices", response_model=List[schemas.Device])
async def list_devices(
    skip: int = 0,
    limit: int = 100,
    organization_id: Optional[str] = None,
    current_user: schemas.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all devices for user's organization"""
    org_id = UUID(current_user.organization_id)
    result = await db.execute(
        select(Device).where(Device.organization_id == org_id).offset(skip).limit(limit)
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
            updated_at=d.updated_at,
        )
        for d in devices
    ]


@router.get("/devices/{device_id}", response_model=schemas.Device)
async def get_device(
    device_id: str,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific device"""
    from uuid import UUID

    try:
        device_uuid = UUID(device_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid device ID format")

    result = await db.execute(
        select(Device).where(
            Device.id == device_uuid,
            Device.organization_id == UUID(current_user.organization_id),
        )
    )
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    return schemas.Device(
        id=str(device.id),
        hostname=device.hostname,
        management_ip=str(device.ip_address),
        vendor=device.vendor,
        device_type=device.device_type,
        role=device.device_role,
        organization_id=str(device.organization_id),
        created_at=device.created_at,
        updated_at=device.updated_at,
    )


@router.post("/devices", response_model=schemas.Device, status_code=201)
async def create_device(
    device: schemas.DeviceCreate,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new device"""
    from uuid import UUID, uuid4

    device_obj = Device(
        id=uuid4(),
        organization_id=UUID(current_user.organization_id),
        hostname=device.hostname,
        ip_address=device.management_ip,
        vendor=device.vendor,
        device_type=device.device_type,
        device_role=device.role,
    )

    db.add(device_obj)
    await db.commit()
    await db.refresh(device_obj)

    return schemas.Device(
        id=str(device_obj.id),
        hostname=device_obj.hostname,
        management_ip=str(device_obj.ip_address),
        vendor=device_obj.vendor,
        device_type=device_obj.device_type,
        role=device_obj.device_role,
        organization_id=str(device_obj.organization_id),
        created_at=device_obj.created_at,
        updated_at=device_obj.updated_at,
    )


@router.patch("/devices/{device_id}", response_model=schemas.Device)
async def update_device(
    device_id: str,
    device_update: schemas.DeviceUpdate,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a device"""
    from uuid import UUID

    try:
        device_uuid = UUID(device_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid device ID format")

    result = await db.execute(
        select(Device).where(
            Device.id == device_uuid,
            Device.organization_id == UUID(current_user.organization_id),
        )
    )
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    update_data = device_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "management_ip":
            setattr(device, "ip_address", value)
        elif field == "role":
            setattr(device, "device_role", value)
        else:
            setattr(device, field, value)

    await db.commit()
    await db.refresh(device)

    return schemas.Device(
        id=str(device.id),
        hostname=device.hostname,
        management_ip=str(device.ip_address),
        vendor=device.vendor,
        device_type=device.device_type,
        role=device.device_role,
        organization_id=str(device.organization_id),
        created_at=device.created_at,
        updated_at=device.updated_at,
    )


@router.delete("/devices/{device_id}", status_code=204)
async def delete_device(
    device_id: str,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a device"""
    from uuid import UUID

    try:
        device_uuid = UUID(device_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid device ID format")

    result = await db.execute(
        select(Device).where(
            Device.id == device_uuid,
            Device.organization_id == UUID(current_user.organization_id),
        )
    )
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    await db.delete(device)
    await db.commit()

    return None


# =============================================================================
# DISCOVERIES
# =============================================================================
@router.post("/discoveries", response_model=schemas.Discovery)
async def trigger_discovery(
    discovery: schemas.DiscoveryCreate,
    current_user: schemas.User = Depends(dependencies.get_current_user),
):
    """Trigger a new discovery"""
    # TODO: Implement discovery logic
    return {"id": "todo", "status": "pending", **discovery.model_dump()}


@router.get("/discoveries/{discovery_id}", response_model=schemas.Discovery)
async def get_discovery(
    discovery_id: str,
    current_user: schemas.User = Depends(dependencies.get_current_user),
):
    """Get discovery status"""
    # TODO: Implement status check
    raise HTTPException(status_code=404, detail="Discovery not found")


# =============================================================================
# AGENT
# =============================================================================
@router.post("/agent/vectors")
async def receive_vectors(
    vectors: schemas.VectorBatch,
    agent_context: dict = Depends(get_agent_auth),
    db: AsyncSession = Depends(get_db),
):
    """Receive vector batch from agent"""
    return {
        "status": "received",
        "count": len(vectors.devices),
        "agent_org": agent_context["organization_id"],
    }


# =============================================================================
# AGENTS
# =============================================================================
@router.get("/agents", response_model=List[schemas.AgentResponse])
async def list_agents(
    skip: int = 0,
    limit: int = 100,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all agents for user's organization"""
    from uuid import UUID
    
    org_id = UUID(current_user.organization_id)
    result = await db.execute(
        select(LocalAgent).where(LocalAgent.organization_id == org_id).offset(skip).limit(limit)
    )
    agents = result.scalars().all()

    return [
        schemas.AgentResponse(
            id=str(a.id),
            organization_id=str(a.organization_id),
            site_id=str(a.site_id) if a.site_id else None,
            name=a.name,
            agent_version=a.agent_version,
            last_seen=a.last_seen,
            is_active=a.is_active,
            capabilities=a.capabilities or {},
            created_at=a.created_at,
            updated_at=a.updated_at,
        )
        for a in agents
    ]


@router.get("/agents/{agent_id}", response_model=schemas.AgentResponse)
async def get_agent(
    agent_id: str,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific agent"""
    from uuid import UUID
    from sqlalchemy import select
    
    try:
        agent_uuid = UUID(agent_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid agent ID format")
    
    result = await db.execute(
        select(LocalAgent).where(
            LocalAgent.id == agent_uuid,
            LocalAgent.organization_id == UUID(current_user.organization_id)
        )
    )
    agent = result.scalar_one_or_none()
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    return schemas.AgentResponse(
        id=str(agent.id),
        organization_id=str(agent.organization_id),
        site_id=str(agent.site_id) if agent.site_id else None,
        name=agent.name,
        agent_version=agent.agent_version,
        last_seen=agent.last_seen,
        is_active=agent.is_active,
        capabilities=agent.capabilities or {},
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


@router.post("/agents/{agent_id}/rotate-key", response_model=schemas.AgentRotateKeyResponse)
async def rotate_agent_key(
    agent_id: str,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Rotate agent API key"""
    import secrets
    from uuid import UUID
    from sqlalchemy import select
    from app.core.security import hash_password
    
    try:
        agent_uuid = UUID(agent_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid agent ID format")
    
    result = await db.execute(
        select(LocalAgent).where(
            LocalAgent.id == agent_uuid,
            LocalAgent.organization_id == UUID(current_user.organization_id)
        )
    )
    agent = result.scalar_one_or_none()
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    new_api_key = f"ndi_agent_{secrets.token_urlsafe(32)}"
    agent.api_key_hash = hash_password(new_api_key)
    
    await db.commit()
    
    return schemas.AgentRotateKeyResponse(
        agent_id=str(agent.id),
        new_api_key=new_api_key,
        message="Save this API key - it won't be shown again"
    )


@router.post("/agents/{agent_id}/heartbeat", response_model=schemas.HeartbeatResponse)
async def agent_heartbeat(
    agent_id: str,
    heartbeat: schemas.HeartbeatRequest,
    db: AsyncSession = Depends(get_db),
):
    """Agent heartbeat - updates last_seen, agent_version, capabilities"""
    from uuid import UUID
    from sqlalchemy import select
    from datetime import datetime, timezone
    
    try:
        agent_uuid = UUID(agent_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid agent ID format")
    
    result = await db.execute(
        select(LocalAgent).where(LocalAgent.id == agent_uuid)
    )
    agent = result.scalar_one_or_none()
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    agent.last_seen = datetime.now(timezone.utc)
    if heartbeat.agent_version:
        agent.agent_version = heartbeat.agent_version
    if heartbeat.capabilities:
        agent.capabilities = heartbeat.capabilities
    
    await db.commit()
    
    return schemas.HeartbeatResponse(
        status="ok",
        agent_id=str(agent.id),
        last_seen=agent.last_seen
    )


# =============================================================================
# PATH VISUALIZER
# =============================================================================
@router.post("/path/trace", response_model=schemas.PathResult)
async def trace_path(
    path_request: schemas.PathTraceRequest,
    current_user: schemas.User = Depends(dependencies.get_current_user),
):
    """Trace path between two IPs"""
    # TODO: Implement path tracing
    raise HTTPException(status_code=501, detail="Not implemented")


# =============================================================================
# SITES
# =============================================================================
@router.get("/sites", response_model=List[schemas.SiteResponse])
async def list_sites(
    skip: int = 0,
    limit: int = 100,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all sites for user's organization"""
    from uuid import UUID

    org_id = UUID(current_user.organization_id)
    result = await db.execute(
        select(Site).where(Site.organization_id == org_id).offset(skip).limit(limit)
    )
    sites = result.scalars().all()

    return [
        schemas.SiteResponse(
            id=str(s.id),
            name=s.name,
            description=s.description,
            site_type=s.site_type,
            location_address=s.location_address,
            timezone=s.timezone,
            organization_id=str(s.organization_id),
            is_active=s.is_active,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in sites
    ]


@router.get("/sites/{site_id}", response_model=schemas.SiteResponse)
async def get_site(
    site_id: str,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific site"""
    from uuid import UUID

    try:
        site_uuid = UUID(site_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid site ID format")

    result = await db.execute(
        select(Site).where(
            Site.id == site_uuid,
            Site.organization_id == UUID(current_user.organization_id),
        )
    )
    site = result.scalar_one_or_none()

    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    return schemas.SiteResponse(
        id=str(site.id),
        name=site.name,
        description=site.description,
        site_type=site.site_type,
        location_address=site.location_address,
        timezone=site.timezone,
        organization_id=str(site.organization_id),
        is_active=site.is_active,
        created_at=site.created_at,
        updated_at=site.updated_at,
    )


@router.post("/sites", response_model=schemas.SiteResponse, status_code=201)
async def create_site(
    site: schemas.SiteCreate,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new site"""
    from uuid import UUID, uuid4

    site_obj = Site(
        id=uuid4(),
        organization_id=UUID(current_user.organization_id),
        name=site.name,
        description=site.description,
        site_type=site.site_type,
        location_address=site.location_address,
        timezone=site.timezone,
        is_active=True,
    )

    db.add(site_obj)
    await db.commit()
    await db.refresh(site_obj)

    return schemas.SiteResponse(
        id=str(site_obj.id),
        name=site_obj.name,
        description=site_obj.description,
        site_type=site_obj.site_type,
        location_address=site_obj.location_address,
        timezone=site_obj.timezone,
        organization_id=str(site_obj.organization_id),
        is_active=site_obj.is_active,
        created_at=site_obj.created_at,
        updated_at=site_obj.updated_at,
    )


@router.patch("/sites/{site_id}", response_model=schemas.SiteResponse)
async def update_site(
    site_id: str,
    site_update: schemas.SiteUpdate,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a site"""
    from uuid import UUID

    try:
        site_uuid = UUID(site_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid site ID format")

    result = await db.execute(
        select(Site).where(
            Site.id == site_uuid,
            Site.organization_id == UUID(current_user.organization_id),
        )
    )
    site = result.scalar_one_or_none()

    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    update_data = site_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(site, field, value)

    await db.commit()
    await db.refresh(site)

    return schemas.SiteResponse(
        id=str(site.id),
        name=site.name,
        description=site.description,
        site_type=site.site_type,
        location_address=site.location_address,
        timezone=site.timezone,
        organization_id=str(site.organization_id),
        is_active=site.is_active,
        created_at=site.created_at,
        updated_at=site.updated_at,
    )


@router.delete("/sites/{site_id}", status_code=204)
async def delete_site(
    site_id: str,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a site"""
    from uuid import UUID

    try:
        site_uuid = UUID(site_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid site ID format")

    result = await db.execute(
        select(Site).where(
            Site.id == site_uuid,
            Site.organization_id == UUID(current_user.organization_id),
        )
    )
    site = result.scalar_one_or_none()

    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    await db.delete(site)
    await db.commit()

    return None
