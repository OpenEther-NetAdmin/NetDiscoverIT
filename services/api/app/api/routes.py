"""
API Routes
"""

from uuid import UUID
from fastapi import APIRouter, HTTPException, Depends, Request, WebSocket, WebSocketDisconnect
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import schemas
from app.api import dependencies
from app.api.dependencies import get_db, get_current_user, get_agent_auth
from app.models.models import Device, Site, LocalAgent, Discovery
from app.core.config import settings
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)


def get_rate_limit(request: Request) -> str:
    """Determine rate limit based on request method"""
    if request.method in ["POST", "PATCH", "DELETE", "PUT"]:
        return settings.RATE_LIMIT_WRITE
    return settings.RATE_LIMIT_READ

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

    await dependencies.audit_log(
        action="device.list",
        resource_type="device",
        outcome="success",
        current_user=current_user,
        db=db,
    )

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

    await dependencies.audit_log(
        action="device.view",
        resource_type="device",
        resource_id=device_id,
        resource_name=device.hostname,
        outcome="success",
        current_user=current_user,
        db=db,
    )

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
    request: Request,
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

    await dependencies.audit_log(
        action="device.create",
        resource_type="device",
        resource_id=str(device_obj.id),
        resource_name=device_obj.hostname,
        outcome="success",
        current_user=current_user,
        db=db,
    )

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
    request: Request,
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

    await dependencies.audit_log(
        action="device.update",
        resource_type="device",
        resource_id=device_id,
        resource_name=device.hostname,
        outcome="success",
        current_user=current_user,
        db=db,
    )

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
    request: Request,
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

    await dependencies.audit_log(
        action="device.delete",
        resource_type="device",
        resource_id=device_id,
        resource_name=device.hostname,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return None


# =============================================================================
# DISCOVERIES
# =============================================================================
@router.post("/discoveries", response_model=schemas.Discovery)
async def trigger_discovery(
    discovery: schemas.DiscoveryCreate,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger a new discovery"""
    from uuid import UUID, uuid4
    from datetime import datetime, timezone
    import json
    import redis

    org_id = UUID(current_user.organization_id)
    discovery_id = uuid4()

    discovery_obj = Discovery(
        id=discovery_id,
        organization_id=org_id,
        created_by=UUID(current_user.id),
        name=discovery.name,
        discovery_type=discovery.discovery_type,
        targets={},
        status="pending",
        progress=0,
    )

    db.add(discovery_obj)
    await db.commit()
    await db.refresh(discovery_obj)

    try:
        redis_client = redis.from_url(settings.REDIS_URL)
        job_data = {
            "discovery_id": str(discovery_id),
            "organization_id": str(org_id),
            "name": discovery.name,
            "discovery_type": discovery.discovery_type,
            "scan_profile": "standard",
        }
        redis_client.lpush("discovery:jobs", json.dumps(job_data))
        redis_client.close()
    except Exception as e:
        import logging
        logging.warning(f"Failed to queue discovery job: {e}")

    await dependencies.audit_log(
        action="discovery.create",
        resource_type="discovery",
        resource_id=str(discovery_id),
        resource_name=discovery.name,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return schemas.Discovery(
        id=str(discovery_obj.id),
        organization_id=str(discovery_obj.organization_id),
        name=discovery_obj.name,
        discovery_type=discovery_obj.discovery_type or "full",
        status="pending",
        device_count=0,
        created_at=discovery_obj.created_at,
        completed_at=None,
    )


@router.get("/discoveries/{discovery_id}", response_model=schemas.Discovery)
async def get_discovery(
    discovery_id: str,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get discovery status"""
    from uuid import UUID
    from sqlalchemy import select

    try:
        discovery_uuid = UUID(discovery_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid discovery ID format")

    result = await db.execute(
        select(Discovery).where(
            Discovery.id == discovery_uuid,
            Discovery.organization_id == UUID(current_user.organization_id),
        )
    )
    discovery = result.scalar_one_or_none()

    if not discovery:
        raise HTTPException(status_code=404, detail="Discovery not found")

    await dependencies.audit_log(
        action="discovery.view",
        resource_type="discovery",
        resource_id=discovery_id,
        resource_name=discovery.name,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return schemas.Discovery(
        id=str(discovery.id),
        organization_id=str(discovery.organization_id),
        name=discovery.name,
        discovery_type=discovery.discovery_type or "full",
        status=discovery.status,
        device_count=discovery.results.get("device_count", 0) if discovery.results else 0,
        created_at=discovery.created_at,
        completed_at=discovery.completed_at,
    )


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
        select(LocalAgent)
        .where(LocalAgent.organization_id == org_id)
        .offset(skip)
        .limit(limit)
    )
    agents = result.scalars().all()

    await dependencies.audit_log(
        action="agent.list",
        resource_type="agent",
        outcome="success",
        current_user=current_user,
        db=db,
    )

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
            LocalAgent.organization_id == UUID(current_user.organization_id),
        )
    )
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    await dependencies.audit_log(
        action="agent.view",
        resource_type="agent",
        resource_id=agent_id,
        resource_name=agent.name,
        outcome="success",
        current_user=current_user,
        db=db,
    )

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


@router.post(
    "/agents/{agent_id}/rotate-key", response_model=schemas.AgentRotateKeyResponse
)
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
            LocalAgent.organization_id == UUID(current_user.organization_id),
        )
    )
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    new_api_key = f"ndi_agent_{secrets.token_urlsafe(32)}"
    agent.api_key_hash = hash_password(new_api_key)

    await db.commit()

    await dependencies.audit_log(
        action="agent.rotate_key",
        resource_type="agent",
        resource_id=agent_id,
        resource_name=agent.name,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return schemas.AgentRotateKeyResponse(
        agent_id=str(agent.id),
        new_api_key=new_api_key,
        message="Save this API key - it won't be shown again",
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

    result = await db.execute(select(LocalAgent).where(LocalAgent.id == agent_uuid))
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent.last_seen = datetime.now(timezone.utc)
    if heartbeat.agent_version:
        agent.agent_version = heartbeat.agent_version
    if heartbeat.capabilities:
        agent.capabilities = heartbeat.capabilities

    await db.commit()

    await dependencies.audit_log(
        action="agent.heartbeat",
        resource_type="agent",
        resource_id=agent_id,
        resource_name=agent.name,
        outcome="success",
        current_user=None,
        db=db,
    )

    return schemas.HeartbeatResponse(
        status="ok", agent_id=str(agent.id), last_seen=agent.last_seen
    )


@router.post(
    "/agents/{agent_id}/upload",
    response_model=schemas.AgentUploadResponse,
    dependencies=[Depends(dependencies.get_agent_auth)],
)
async def upload_agent_data(
    agent_id: str,
    request: schemas.AgentUploadRequest,
    db: AsyncSession = Depends(get_db),
    agent_auth: dict = Depends(dependencies.get_agent_auth),
):
    """
    Upload device metadata batches from agent.
    
    Accepts device metadata collected by local agent.
    Creates/updates Device records in cloud PostgreSQL.
    """
    from uuid import UUID
    from sqlalchemy import select, func
    from app.models.models import Device
    
    try:
        agent_uuid = UUID(agent_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid agent_id format")
    
    org_id = UUID(agent_auth["organization_id"])
    
    uploaded = 0
    updated = 0
    errors = []
    
    for device_data in request.devices:
        try:
            existing = None
            if device_data.ip_address:
                result = await db.execute(
                    select(Device).where(
                        Device.organization_id == org_id,
                        Device.ip_address == device_data.ip_address
                    )
                )
                existing = result.scalar_one_or_none()
            
            if existing:
                for field, value in {
                    "hostname": device_data.hostname,
                    "mac_address": device_data.mac_address,
                    "device_type": device_data.device_type,
                    "vendor": device_data.vendor,
                    "model": device_data.model,
                    "os_version": device_data.os_version,
                    "metadata": device_data.metadata,
                    "config_hash": device_data.config_hash,
                    "last_seen": func.now(),
                }.items():
                    if value is not None:
                        setattr(existing, field, value)
                updated += 1
            else:
                new_device = Device(
                    id=uuid4(),
                    organization_id=org_id,
                    site_id=UUID(device_data.site_id) if device_data.site_id else None,
                    hostname=device_data.hostname,
                    ip_address=device_data.ip_address,
                    mac_address=device_data.mac_address,
                    device_type=device_data.device_type,
                    vendor=device_data.vendor,
                    model=device_data.model,
                    os_version=device_data.os_version,
                    metadata=device_data.metadata,
                    config_hash=device_data.config_hash,
                    discovered_at=func.now(),
                    last_seen=func.now(),
                )
                db.add(new_device)
                uploaded += 1
            
        except Exception as e:
            errors.append(f"Device {device_data.hostname or device_data.ip_address}: {str(e)}")
    
    await db.commit()
    
    return schemas.AgentUploadResponse(
        uploaded=uploaded,
        updated=updated,
        errors=errors,
    )


# =============================================================================
# PATH VISUALIZER
# =============================================================================
@router.post("/path/trace", response_model=schemas.PathResult)
async def trace_path(
    path_request: schemas.PathTraceRequest,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trace path between two IPs"""
    from uuid import UUID
    from sqlalchemy import select
    from app.db.neo4j import get_neo4j_client

    org_id = UUID(current_user.organization_id)

    result = await db.execute(
        select(Device).where(
            Device.organization_id == org_id,
            Device.ip_address == path_request.source_ip,
        )
    )
    source_device = result.scalar_one_or_none()

    result = await db.execute(
        select(Device).where(
            Device.organization_id == org_id,
            Device.ip_address == path_request.destination_ip,
        )
    )
    dest_device = result.scalar_one_or_none()

    if not source_device or not dest_device:
        return schemas.PathResult(
            path_found=False,
            hops=[],
            summary={"error": "Source or destination device not found"},
            analysis={},
            issues=[{"type": "device_not_found", "message": "One or both devices not found in database"}],
        )

    try:
        neo4j_client = await get_neo4j_client()
        path_nodes = await neo4j_client.find_path(
            source_device.hostname, dest_device.hostname
        )

        if not path_nodes:
            return schemas.PathResult(
                path_found=False,
                hops=[],
                summary={"message": "No path found between devices"},
                analysis={},
                issues=[{"type": "no_path", "message": "No connectivity path found in topology"}],
            )

        hops = []
        for i, node in enumerate(path_nodes):
            hops.append(
                schemas.PathHop(
                    hop=i + 1,
                    device={"hostname": node.get("hostname"), "ip_address": node.get("ip_address")},
                    interface={"name": "unknown"},
                    egress={"name": "unknown"},
                )
            )

        await dependencies.audit_log(
            action="path.trace",
            resource_type="path",
            resource_name=f"{path_request.source_ip} -> {path_request.destination_ip}",
            outcome="success",
            current_user=current_user,
            db=db,
        )

        return schemas.PathResult(
            path_found=True,
            hops=hops,
            summary={
                "total_hops": len(hops),
                "source": path_request.source_ip,
                "destination": path_request.destination_ip,
            },
            analysis={"path_length": len(hops)},
            issues=[],
        )

    except Exception as e:
        import logging
        logging.error(f"Path trace error: {e}")
        return schemas.PathResult(
            path_found=False,
            hops=[],
            summary={"error": str(e)},
            analysis={},
            issues=[{"type": "trace_error", "message": "Failed to trace path"}],
        )


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

    await dependencies.audit_log(
        action="site.list",
        resource_type="site",
        outcome="success",
        current_user=current_user,
        db=db,
    )

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

    await dependencies.audit_log(
        action="site.view",
        resource_type="site",
        resource_id=site_id,
        resource_name=site.name,
        outcome="success",
        current_user=current_user,
        db=db,
    )

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

    await dependencies.audit_log(
        action="site.create",
        resource_type="site",
        resource_id=str(site_obj.id),
        resource_name=site_obj.name,
        outcome="success",
        current_user=current_user,
        db=db,
    )

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

    await dependencies.audit_log(
        action="site.update",
        resource_type="site",
        resource_id=site_id,
        resource_name=site.name,
        outcome="success",
        current_user=current_user,
        db=db,
    )

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

    await dependencies.audit_log(
        action="site.delete",
        resource_type="site",
        resource_id=site_id,
        resource_name=site.name,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return None


# =============================================================================
# ALERTS
# =============================================================================
@router.get("/alerts/rules", response_model=List[schemas.AlertRuleResponse])
async def list_alert_rules(
    skip: int = 0,
    limit: int = 100,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all alert rules for user's organization"""
    from uuid import UUID
    from sqlalchemy import select
    from app.models.models import AlertRule

    org_id = UUID(current_user.organization_id)
    result = await db.execute(
        select(AlertRule)
        .where(AlertRule.organization_id == org_id)
        .offset(skip)
        .limit(limit)
    )
    rules = result.scalars().all()

    await dependencies.audit_log(
        action="alert_rule.list",
        resource_type="alert_rule",
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return [
        schemas.AlertRuleResponse(
            id=str(r.id),
            organization_id=str(r.organization_id),
            name=r.name,
            rule_type=r.rule_type,
            conditions=r.conditions,
            severity=r.severity,
            notify_integration_ids=r.notify_integration_ids or [],
            site_ids=r.site_ids or [],
            device_ids=r.device_ids or [],
            is_enabled=r.is_enabled,
            created_by=str(r.created_by) if r.created_by else None,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rules
    ]


@router.get("/alerts/rules/{rule_id}", response_model=schemas.AlertRuleResponse)
async def get_alert_rule(
    rule_id: str,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific alert rule"""
    from uuid import UUID
    from sqlalchemy import select
    from app.models.models import AlertRule

    try:
        rule_uuid = UUID(rule_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid alert rule ID format")

    result = await db.execute(
        select(AlertRule).where(
            AlertRule.id == rule_uuid,
            AlertRule.organization_id == UUID(current_user.organization_id),
        )
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found")

    await dependencies.audit_log(
        action="alert_rule.view",
        resource_type="alert_rule",
        resource_id=rule_id,
        resource_name=rule.name,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return schemas.AlertRuleResponse(
        id=str(rule.id),
        organization_id=str(rule.organization_id),
        name=rule.name,
        rule_type=rule.rule_type,
        conditions=rule.conditions,
        severity=rule.severity,
        notify_integration_ids=rule.notify_integration_ids or [],
        site_ids=rule.site_ids or [],
        device_ids=rule.device_ids or [],
        is_enabled=rule.is_enabled,
        created_by=str(rule.created_by) if rule.created_by else None,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


@router.post("/alerts/rules", response_model=schemas.AlertRuleResponse, status_code=201)
async def create_alert_rule(
    rule: schemas.AlertRuleCreate,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new alert rule"""
    from uuid import UUID, uuid4
    from sqlalchemy import select
    from app.models.models import AlertRule

    org_id = UUID(current_user.organization_id)

    rule_obj = AlertRule(
        id=uuid4(),
        organization_id=org_id,
        name=rule.name,
        rule_type=rule.rule_type,
        conditions=rule.conditions,
        severity=rule.severity,
        notify_integration_ids=rule.notify_integration_ids,
        site_ids=rule.site_ids,
        device_ids=rule.device_ids,
        is_enabled=rule.is_enabled,
        created_by=UUID(current_user.id),
    )

    db.add(rule_obj)
    await db.commit()
    await db.refresh(rule_obj)

    await dependencies.audit_log(
        action="alert_rule.create",
        resource_type="alert_rule",
        resource_id=str(rule_obj.id),
        resource_name=rule_obj.name,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return schemas.AlertRuleResponse(
        id=str(rule_obj.id),
        organization_id=str(rule_obj.organization_id),
        name=rule_obj.name,
        rule_type=rule_obj.rule_type,
        conditions=rule_obj.conditions,
        severity=rule_obj.severity,
        notify_integration_ids=rule_obj.notify_integration_ids or [],
        site_ids=rule_obj.site_ids or [],
        device_ids=rule_obj.device_ids or [],
        is_enabled=rule_obj.is_enabled,
        created_by=str(rule_obj.created_by) if rule_obj.created_by else None,
        created_at=rule_obj.created_at,
        updated_at=rule_obj.updated_at,
    )


@router.patch("/alerts/rules/{rule_id}", response_model=schemas.AlertRuleResponse)
async def update_alert_rule(
    rule_id: str,
    rule_update: schemas.AlertRuleUpdate,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an alert rule"""
    from uuid import UUID
    from sqlalchemy import select
    from app.models.models import AlertRule

    try:
        rule_uuid = UUID(rule_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid alert rule ID format")

    result = await db.execute(
        select(AlertRule).where(
            AlertRule.id == rule_uuid,
            AlertRule.organization_id == UUID(current_user.organization_id),
        )
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found")

    update_data = rule_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(rule, field, value)

    await db.commit()
    await db.refresh(rule)

    await dependencies.audit_log(
        action="alert_rule.update",
        resource_type="alert_rule",
        resource_id=rule_id,
        resource_name=rule.name,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return schemas.AlertRuleResponse(
        id=str(rule.id),
        organization_id=str(rule.organization_id),
        name=rule.name,
        rule_type=rule.rule_type,
        conditions=rule.conditions,
        severity=rule.severity,
        notify_integration_ids=rule.notify_integration_ids or [],
        site_ids=rule.site_ids or [],
        device_ids=rule.device_ids or [],
        is_enabled=rule.is_enabled,
        created_by=str(rule.created_by) if rule.created_by else None,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


@router.delete("/alerts/rules/{rule_id}", status_code=204)
async def delete_alert_rule(
    rule_id: str,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an alert rule"""
    from uuid import UUID
    from sqlalchemy import select
    from app.models.models import AlertRule

    try:
        rule_uuid = UUID(rule_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid alert rule ID format")

    result = await db.execute(
        select(AlertRule).where(
            AlertRule.id == rule_uuid,
            AlertRule.organization_id == UUID(current_user.organization_id),
        )
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found")

    await db.delete(rule)
    await db.commit()

    await dependencies.audit_log(
        action="alert_rule.delete",
        resource_type="alert_rule",
        resource_id=rule_id,
        resource_name=rule.name,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return None


@router.get("/alerts/events", response_model=List[schemas.AlertEventResponse])
async def list_alert_events(
    skip: int = 0,
    limit: int = 100,
    severity: Optional[str] = None,
    acknowledged: Optional[bool] = None,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all alert events for user's organization"""
    from uuid import UUID
    from sqlalchemy import select
    from app.models.models import AlertEvent

    org_id = UUID(current_user.organization_id)

    query = select(AlertEvent).where(AlertEvent.organization_id == org_id)

    if severity:
        query = query.where(AlertEvent.severity == severity)

    if acknowledged is not None:
        if acknowledged:
            query = query.where(AlertEvent.acknowledged_at.isnot(None))
        else:
            query = query.where(AlertEvent.acknowledged_at.is_(None))

    query = query.offset(skip).limit(limit).order_by(AlertEvent.created_at.desc())

    result = await db.execute(query)
    events = result.scalars().all()

    await dependencies.audit_log(
        action="alert_event.list",
        resource_type="alert_event",
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return [
        schemas.AlertEventResponse(
            id=str(e.id),
            organization_id=str(e.organization_id),
            rule_id=str(e.rule_id),
            device_id=str(e.device_id) if e.device_id else None,
            agent_id=str(e.agent_id) if e.agent_id else None,
            severity=e.severity,
            title=e.title,
            details=e.details,
            notifications_sent=e.notifications_sent or [],
            acknowledged_by=str(e.acknowledged_by) if e.acknowledged_by else None,
            acknowledged_at=e.acknowledged_at,
            resolved_at=e.resolved_at,
            resolution_notes=e.resolution_notes,
            created_at=e.created_at,
        )
        for e in events
    ]


@router.get("/alerts/events/{event_id}", response_model=schemas.AlertEventResponse)
async def get_alert_event(
    event_id: str,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific alert event"""
    from uuid import UUID
    from sqlalchemy import select
    from app.models.models import AlertEvent

    try:
        event_uuid = UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid alert event ID format")

    result = await db.execute(
        select(AlertEvent).where(
            AlertEvent.id == event_uuid,
            AlertEvent.organization_id == UUID(current_user.organization_id),
        )
    )
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(status_code=404, detail="Alert event not found")

    await dependencies.audit_log(
        action="alert_event.view",
        resource_type="alert_event",
        resource_id=event_id,
        resource_name=event.title,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return schemas.AlertEventResponse(
        id=str(event.id),
        organization_id=str(event.organization_id),
        rule_id=str(event.rule_id),
        device_id=str(event.device_id) if event.device_id else None,
        agent_id=str(event.agent_id) if event.agent_id else None,
        severity=event.severity,
        title=event.title,
        details=event.details,
        notifications_sent=event.notifications_sent or [],
        acknowledged_by=str(event.acknowledged_by) if event.acknowledged_by else None,
        acknowledged_at=event.acknowledged_at,
        resolved_at=event.resolved_at,
        resolution_notes=event.resolution_notes,
        created_at=event.created_at,
    )


@router.post("/alerts/events/{event_id}/acknowledge", response_model=schemas.AlertEventResponse)
async def acknowledge_alert_event(
    event_id: str,
    acknowledge: schemas.AlertEventAcknowledge,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Acknowledge an alert event"""
    from uuid import UUID
    from sqlalchemy import select
    from app.models.models import AlertEvent
    from datetime import datetime, timezone

    try:
        event_uuid = UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid alert event ID format")

    result = await db.execute(
        select(AlertEvent).where(
            AlertEvent.id == event_uuid,
            AlertEvent.organization_id == UUID(current_user.organization_id),
        )
    )
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(status_code=404, detail="Alert event not found")

    event.acknowledged_by = UUID(current_user.id)
    event.acknowledged_at = datetime.now(timezone.utc)
    if acknowledge.resolution_notes:
        event.resolution_notes = acknowledge.resolution_notes

    await db.commit()
    await db.refresh(event)

    await dependencies.audit_log(
        action="alert_event.acknowledge",
        resource_type="alert_event",
        resource_id=event_id,
        resource_name=event.title,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return schemas.AlertEventResponse(
        id=str(event.id),
        organization_id=str(event.organization_id),
        rule_id=str(event.rule_id),
        device_id=str(event.device_id) if event.device_id else None,
        agent_id=str(event.agent_id) if event.agent_id else None,
        severity=event.severity,
        title=event.title,
        details=event.details,
        notifications_sent=event.notifications_sent or [],
        acknowledged_by=str(event.acknowledged_by) if event.acknowledged_by else None,
        acknowledged_at=event.acknowledged_at,
        resolved_at=event.resolved_at,
        resolution_notes=event.resolution_notes,
        created_at=event.created_at,
    )


# =============================================================================
# INTEGRATION CONFIGS
# =============================================================================
@router.get("/integrations", response_model=List[schemas.IntegrationConfigResponse])
async def list_integrations(
    request: Request,
    skip: int = 0,
    limit: int = 100,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all integrations for users organization"""
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
    request: Request,
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
    request: Request,
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

    result = await db.execute(
        select(IntegrationConfig).where(
            IntegrationConfig.organization_id == org_id,
            IntegrationConfig.name == integration.name,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Integration with this name already exists")

    credentials_json = json.dumps(integration.credentials)
    encrypted_creds = None
    if integration.credentials:
        from cryptography.fernet import Fernet
        from app.core.config import settings
        fernet = Fernet(settings.CREDENTIAL_ENCRYPTION_KEY.encode())
        encrypted_creds = fernet.encrypt(credentials_json.encode()).decode()

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
    request: Request,
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

    if "credentials" in update_data and update_data["credentials"]:
        from cryptography.fernet import Fernet
        from app.core.config import settings
        fernet = Fernet(settings.CREDENTIAL_ENCRYPTION_KEY.encode())
        credentials_json = json.dumps(update_data["credentials"])
        integration.encrypted_credentials = fernet.encrypt(credentials_json.encode()).decode()
        del update_data["credentials"]

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
    request: Request,
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
    request: Request,
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
    import httpx

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
            if not credentials or not base_url:
                return {"success": False, "message": "Missing credentials or base_url"}
            
            async with httpx.AsyncClient() as client:
                headers = {
                    "Authorization": f"Basic " + credentials.get("api_token", ""),
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


# =============================================================================
# WEBSOCKET
# =============================================================================
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
    from app.api.websocket import manager

    await manager.connect(websocket, discovery_id)
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        manager.disconnect(websocket, discovery_id)
