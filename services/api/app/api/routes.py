"""
API Routes
"""

from uuid import UUID
from fastapi import (
    APIRouter,
    HTTPException,
    Depends,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import schemas
from app.api import dependencies
from app.api.dependencies import get_db, get_current_user, get_agent_auth, get_rate_limit
from app.models.models import Device, Site, LocalAgent, Discovery, ACLSnapshot, AuditLog
from app.core.config import settings
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)


router = APIRouter()


# =============================================================================
# HEALTH
# =============================================================================
@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


@router.get("/portal/overview", response_model=schemas.PortalOverview)
async def portal_overview(
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return MSP portal summary metrics for the current organization"""
    from app.models.models import AlertEvent, Discovery

    org_id = UUID(current_user.organization_id)

    total_devices_result = await db.execute(
        select(Device.id).where(Device.organization_id == org_id)
    )
    total_devices = len(total_devices_result.scalars().all())

    active_discoveries_result = await db.execute(
        select(Discovery).where(
            Discovery.organization_id == org_id,
            Discovery.status == "running",
        )
    )
    active_discoveries = len(active_discoveries_result.scalars().all())

    alerts_result = await db.execute(
        select(AlertEvent).where(AlertEvent.organization_id == org_id)
    )
    alerts = alerts_result.scalars().all()
    total_alerts = len(alerts)
    open_alerts = len([alert for alert in alerts if alert.resolved_at is None])

    recent_devices_result = await db.execute(
        select(Device)
        .where(Device.organization_id == org_id)
        .order_by(Device.updated_at.desc())
        .limit(5)
    )
    recent_devices = recent_devices_result.scalars().all()

    recent_discoveries_result = await db.execute(
        select(Discovery)
        .where(Discovery.organization_id == org_id)
        .order_by(Discovery.created_at.desc())
        .limit(5)
    )
    recent_discoveries = recent_discoveries_result.scalars().all()

    return schemas.PortalOverview(
        total_devices=total_devices,
        active_discoveries=active_discoveries,
        total_alerts=total_alerts,
        open_alerts=open_alerts,
        recent_devices=[
            schemas.Device(
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
            for device in recent_devices
        ],
        recent_discoveries=[
            schemas.Discovery(
                id=str(discovery.id),
                organization_id=str(discovery.organization_id),
                name=discovery.name,
                discovery_type=discovery.discovery_type,
                status=discovery.status,
                device_count=discovery.device_count or 0,
                created_at=discovery.created_at,
                completed_at=discovery.completed_at,
            )
            for discovery in recent_discoveries
        ],
    )


def _site_response(site_obj: Site) -> schemas.SiteResponse:
    """Build a site response with safe timestamp defaults."""
    from datetime import datetime, timezone

    created_at = site_obj.created_at or datetime.now(timezone.utc)
    updated_at = site_obj.updated_at or created_at

    return schemas.SiteResponse(
        id=str(site_obj.id),
        name=site_obj.name,
        description=site_obj.description,
        site_type=site_obj.site_type,
        location_address=site_obj.location_address,
        timezone=site_obj.timezone,
        organization_id=str(site_obj.organization_id),
        is_active=site_obj.is_active,
        created_at=created_at,
        updated_at=updated_at,
    )


def _device_response(device_obj: Device) -> schemas.Device:
    """Build a device response with safe timestamp defaults."""
    from datetime import datetime, timezone

    created_at = getattr(device_obj, "created_at", None) or getattr(device_obj, "discovered_at", None) or datetime.now(timezone.utc)
    updated_at = getattr(device_obj, "updated_at", None) or getattr(device_obj, "last_seen", None) or created_at

    return schemas.Device(
        id=str(device_obj.id),
        hostname=device_obj.hostname,
        management_ip=str(device_obj.ip_address),
        vendor=device_obj.vendor,
        device_type=device_obj.device_type,
        role=device_obj.device_role,
        organization_id=str(device_obj.organization_id),
        created_at=created_at,
        updated_at=updated_at,
    )


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

    return [_device_response(d) for d in devices]


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
    if device is None and hasattr(result, "scalars"):
        scalar_result = result.scalars()
        if hasattr(scalar_result, "first"):
            device = scalar_result.first()

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

    return _device_response(device)


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

    return _device_response(device_obj)


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
    if device is None and hasattr(result, "scalars"):
        scalar_result = result.scalars()
        if hasattr(scalar_result, "first"):
            device = scalar_result.first()

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

    return _device_response(device)


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
        device_count=(
            discovery.results.get("device_count", 0) if discovery.results else 0
        ),
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
    from uuid import UUID, uuid4
    from sqlalchemy import select, func
    from app.models.models import Device

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
                        Device.ip_address == device_data.ip_address,
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
                    "meta": device_data.metadata,
                    "config_hash": device_data.config_hash,
                    "last_seen": func.now(),
                }.items():
                    if value is not None:
                        setattr(existing, field, value)
                if device_data.role_vector is not None:
                    existing.role_vector = device_data.role_vector
                if device_data.topology_vector is not None:
                    existing.topology_vector = device_data.topology_vector
                if device_data.security_vector is not None:
                    existing.security_vector = device_data.security_vector
                if device_data.config_vector is not None:
                    existing.config_vector = device_data.config_vector
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
                    meta=device_data.metadata,
                    config_hash=device_data.config_hash,
                    role_vector=device_data.role_vector,
                    topology_vector=device_data.topology_vector,
                    security_vector=device_data.security_vector,
                    config_vector=device_data.config_vector,
                    discovered_at=func.now(),
                    last_seen=func.now(),
                )
                db.add(new_device)
                uploaded += 1

        except Exception as e:
            errors.append(
                f"Device {device_data.hostname or device_data.ip_address}: {str(e)}"
            )

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
            issues=[
                {
                    "type": "device_not_found",
                    "message": "One or both devices not found in database",
                }
            ],
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
                issues=[
                    {
                        "type": "no_path",
                        "message": "No connectivity path found in topology",
                    }
                ],
            )

        hops = []
        for i, node in enumerate(path_nodes):
            hops.append(
                schemas.PathHop(
                    hop=i + 1,
                    device={
                        "hostname": node.get("hostname"),
                        "ip_address": node.get("ip_address"),
                    },
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
    if site is None and hasattr(result, "scalars"):
        scalar_result = result.scalars()
        if hasattr(scalar_result, "first"):
            site = scalar_result.first()

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

    return _site_response(site)


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

    return _site_response(site_obj)


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
    if site is None and hasattr(result, "scalars"):
        scalar_result = result.scalars()
        if hasattr(scalar_result, "first"):
            site = scalar_result.first()

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

    return _site_response(site)


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


@router.post(
    "/alerts/events/{event_id}/acknowledge", response_model=schemas.AlertEventResponse
)
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


@router.get(
    "/integrations/{integration_id}", response_model=schemas.IntegrationConfigResponse
)
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


@router.post(
    "/integrations", response_model=schemas.IntegrationConfigResponse, status_code=201
)
async def create_integration(
    request: Request,
    integration: schemas.IntegrationConfigCreate,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new integration config"""
    from uuid import UUID, uuid4
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
        raise HTTPException(
            status_code=400, detail="Integration with this name already exists"
        )

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
        encrypted_webhook_secret = fernet.encrypt(
            integration.webhook_secret.encode()
        ).decode()

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


@router.patch(
    "/integrations/{integration_id}", response_model=schemas.IntegrationConfigResponse
)
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
        integration.encrypted_credentials = fernet.encrypt(
            credentials_json.encode()
        ).decode()
        del update_data["credentials"]

    if "webhook_secret" in update_data and update_data["webhook_secret"]:
        from cryptography.fernet import Fernet
        from app.core.config import settings

        fernet = Fernet(settings.CREDENTIAL_ENCRYPTION_KEY.encode())
        integration.webhook_secret = fernet.encrypt(
            update_data["webhook_secret"].encode()
        ).decode()
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


@router.post(
    "/integrations/{integration_id}/test",
    response_model=schemas.IntegrationConfigTestResponse,
)
async def test_integration(
    request: Request,
    integration_id: str,
    test_request: schemas.IntegrationConfigTestRequest,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Test an integration configuration"""
    from uuid import UUID
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

    credentials = None
    if integration.encrypted_credentials:
        from cryptography.fernet import Fernet
        from app.core.config import settings

        fernet = Fernet(settings.CREDENTIAL_ENCRYPTION_KEY.encode())
        try:
            creds_decrypted = fernet.decrypt(
                integration.encrypted_credentials.encode()
            ).decode()
            credentials = json.loads(creds_decrypted)
        except Exception as e:
            return schemas.IntegrationConfigTestResponse(
                success=False,
                message="Failed to decrypt credentials",
                details={"error": str(e)},
            )

    test_result = await _test_integration(
        integration, credentials, test_request.test_message
    )

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
                return {
                    "success": False,
                    "message": "Missing webhook_url in credentials",
                }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    credentials["webhook_url"],
                    json={"text": test_message or "Test message from NetDiscoverIT"},
                    timeout=10,
                )
                if response.status_code == 200:
                    return {"success": True, "message": "Slack webhook test successful"}
                return {
                    "success": False,
                    "message": f"Slack webhook failed: {response.status_code}",
                }

        elif integration_type == "teams":
            if not credentials or "webhook_url" not in credentials:
                return {
                    "success": False,
                    "message": "Missing webhook_url in credentials",
                }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    credentials["webhook_url"],
                    json={"text": test_message or "Test message from NetDiscoverIT"},
                    timeout=10,
                )
                if response.status_code == 200:
                    return {"success": True, "message": "Teams webhook test successful"}
                return {
                    "success": False,
                    "message": f"Teams webhook failed: {response.status_code}",
                }

        elif integration_type == "servicenow":
            if not credentials or not base_url:
                return {"success": False, "message": "Missing credentials or base_url"}

            async with httpx.AsyncClient() as client:
                auth = (
                    credentials.get("username", ""),
                    credentials.get("password", ""),
                )
                response = await client.get(
                    f"{base_url}/api/now/table/change_request",
                    auth=auth,
                    params={"sysparm_limit": 1},
                    timeout=10,
                )
                if response.status_code == 200:
                    return {
                        "success": True,
                        "message": "ServiceNow API test successful",
                    }
                return {
                    "success": False,
                    "message": f"ServiceNow API failed: {response.status_code}",
                }

        elif integration_type == "jira":
            if not credentials or not base_url:
                return {"success": False, "message": "Missing credentials or base_url"}

            async with httpx.AsyncClient() as client:
                headers = {
                    "Authorization": "Basic " + credentials.get("api_token", ""),
                    "Content-Type": "application/json",
                }
                response = await client.get(
                    f"{base_url}/rest/api/3/myself",
                    headers=headers,
                    timeout=10,
                )
                if response.status_code == 200:
                    return {"success": True, "message": "JIRA API test successful"}
                return {
                    "success": False,
                    "message": f"JIRA API failed: {response.status_code}",
                }

        elif integration_type == "pagerduty":
            if not credentials or "routing_key" not in credentials:
                return {
                    "success": False,
                    "message": "Missing routing_key in credentials",
                }

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
                return {
                    "success": False,
                    "message": f"PagerDuty failed: {response.status_code}",
                }

        else:
            return {
                "success": False,
                "message": f"Unsupported integration type: {integration_type}",
            }

    except Exception as e:
        return {"success": False, "message": f"Test failed: {str(e)}"}


# =============================================================================
# CHANGE RECORDS
# =============================================================================

from app.services.change_service import VALID_TRANSITIONS, can_transition, generate_change_number


TRANSITION_ROLES = {
    "approve": "admin",
    "verify": "admin",
    "rollback": "admin",
}


@router.post("/changes", response_model=schemas.ChangeRecordResponse, status_code=201)
async def create_change_record(
    change: schemas.ChangeRecordCreate,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new change record (status=draft)"""
    from uuid import UUID, uuid4
    from app.models.models import ChangeRecord

    org_id = UUID(current_user.organization_id)
    change_number = await generate_change_number(db)

    change_record = ChangeRecord(
        id=uuid4(),
        organization_id=org_id,
        change_number=change_number,
        status="draft",
        change_type=change.change_type,
        title=change.title,
        description=change.description,
        risk_level=change.risk_level,
        affected_devices=change.affected_devices,
        affected_compliance_scopes=change.affected_compliance_scopes,
        scheduled_window_start=change.scheduled_window_start,
        scheduled_window_end=change.scheduled_window_end,
        compliance_justification=change.compliance_justification,
        requested_by=UUID(current_user.id),
    )

    db.add(change_record)
    await db.commit()
    await db.refresh(change_record)

    await dependencies.audit_log(
        action="change_record.create",
        resource_type="change_record",
        resource_id=str(change_record.id),
        resource_name=change_record.change_number,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return schemas.ChangeRecordResponse(
        id=str(change_record.id),
        organization_id=str(change_record.organization_id),
        change_number=change_record.change_number,
        status=change_record.status,
        change_type=change_record.change_type,
        title=change_record.title,
        description=change_record.description,
        risk_level=change_record.risk_level,
        compliance_justification=change_record.compliance_justification,
        affected_devices=change_record.affected_devices or [],
        affected_compliance_scopes=change_record.affected_compliance_scopes or [],
        requested_by=(
            str(change_record.requested_by) if change_record.requested_by else None
        ),
        requested_at=change_record.requested_at,
        simulation_performed=change_record.simulation_performed,
        simulation_results=change_record.simulation_results,
        simulation_passed=change_record.simulation_passed,
        rollback_performed=change_record.rollback_performed,
        created_at=change_record.created_at,
        updated_at=change_record.updated_at,
    )


@router.get("/changes", response_model=schemas.ChangeRecordListResponse)
async def list_change_records(
    skip: int = 0,
    limit: int = 100,
    status: str | None = None,
    risk_level: str | None = None,
    device_id: str | None = None,
    compliance_scope: str | None = None,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List change records with optional filters"""
    from uuid import UUID
    from sqlalchemy import select, func
    from app.models.models import ChangeRecord

    org_id = UUID(current_user.organization_id)

    query = select(ChangeRecord).where(ChangeRecord.organization_id == org_id)

    if status:
        query = query.where(ChangeRecord.status == status)
    if risk_level:
        query = query.where(ChangeRecord.risk_level == risk_level)
    if device_id:
        query = query.where(ChangeRecord.affected_devices.contains([device_id]))
    if compliance_scope:
        query = query.where(
            ChangeRecord.affected_compliance_scopes.contains([compliance_scope])
        )

    count_query = (
        select(func.count())
        .select_from(ChangeRecord)
        .where(ChangeRecord.organization_id == org_id)
    )
    if status:
        count_query = count_query.where(ChangeRecord.status == status)
    if risk_level:
        count_query = count_query.where(ChangeRecord.risk_level == risk_level)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.offset(skip).limit(limit).order_by(ChangeRecord.requested_at.desc())
    result = await db.execute(query)
    changes = result.scalars().all()

    return schemas.ChangeRecordListResponse(
        items=[
            schemas.ChangeRecordResponse(
                id=str(c.id),
                organization_id=str(c.organization_id),
                change_number=c.change_number,
                status=c.status,
                change_type=c.change_type,
                title=c.title,
                description=c.description,
                risk_level=c.risk_level,
                compliance_justification=c.compliance_justification,
                affected_devices=c.affected_devices or [],
                affected_compliance_scopes=c.affected_compliance_scopes or [],
                requested_by=str(c.requested_by) if c.requested_by else None,
                requested_at=c.requested_at,
                approved_by=str(c.approved_by) if c.approved_by else None,
                approved_at=c.approved_at,
                approval_notes=c.approval_notes,
                proposed_change_hash=c.proposed_change_hash,
                pre_change_hash=c.pre_change_hash,
                post_change_hash=c.post_change_hash,
                simulation_performed=c.simulation_performed,
                simulation_results=c.simulation_results,
                simulation_passed=c.simulation_passed,
                implemented_by=str(c.implemented_by) if c.implemented_by else None,
                implemented_at=c.implemented_at,
                implementation_evidence=c.implementation_evidence,
                verification_results=c.verification_results,
                verification_passed=c.verification_passed,
                rollback_performed=c.rollback_performed,
                rollback_at=c.rollback_at,
                rollback_reason=c.rollback_reason,
                external_ticket_id=c.external_ticket_id,
                external_ticket_url=c.external_ticket_url,
                ticket_system=c.ticket_system,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in changes
        ],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/changes/{change_id}", response_model=schemas.ChangeRecordResponse)
async def get_change_record(
    change_id: str,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific change record"""
    from uuid import UUID
    from sqlalchemy import select
    from fastapi import HTTPException
    from app.models.models import ChangeRecord

    try:
        change_uuid = UUID(change_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid change ID format")

    org_id = UUID(current_user.organization_id)
    result = await db.execute(
        select(ChangeRecord).where(
            ChangeRecord.id == change_uuid,
            ChangeRecord.organization_id == org_id,
        )
    )
    change = result.scalar_one_or_none()

    if not change:
        raise HTTPException(status_code=404, detail="Change record not found")

    return schemas.ChangeRecordResponse(
        id=str(change.id),
        organization_id=str(change.organization_id),
        change_number=change.change_number,
        status=change.status,
        change_type=change.change_type,
        title=change.title,
        description=change.description,
        risk_level=change.risk_level,
        compliance_justification=change.compliance_justification,
        affected_devices=change.affected_devices or [],
        affected_compliance_scopes=change.affected_compliance_scopes or [],
        requested_by=str(change.requested_by) if change.requested_by else None,
        requested_at=change.requested_at,
        approved_by=str(change.approved_by) if change.approved_by else None,
        approved_at=change.approved_at,
        approval_notes=change.approval_notes,
        proposed_change_hash=change.proposed_change_hash,
        pre_change_hash=change.pre_change_hash,
        post_change_hash=change.post_change_hash,
        simulation_performed=change.simulation_performed,
        simulation_results=change.simulation_results,
        simulation_passed=change.simulation_passed,
        implemented_by=str(change.implemented_by) if change.implemented_by else None,
        implemented_at=change.implemented_at,
        implementation_evidence=change.implementation_evidence,
        verification_results=change.verification_results,
        verification_passed=change.verification_passed,
        rollback_performed=change.rollback_performed,
        rollback_at=change.rollback_at,
        rollback_reason=change.rollback_reason,
        external_ticket_id=change.external_ticket_id,
        external_ticket_url=change.external_ticket_url,
        ticket_system=change.ticket_system,
        created_at=change.created_at,
        updated_at=change.updated_at,
    )


@router.patch("/changes/{change_id}", response_model=schemas.ChangeRecordResponse)
async def update_change_record(
    change_id: str,
    change_update: schemas.ChangeRecordUpdate,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a change record (draft/proposed status only)"""
    from uuid import UUID
    from sqlalchemy import select
    from fastapi import HTTPException
    from app.models.models import ChangeRecord

    try:
        change_uuid = UUID(change_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid change ID format")

    org_id = UUID(current_user.organization_id)
    result = await db.execute(
        select(ChangeRecord).where(
            ChangeRecord.id == change_uuid,
            ChangeRecord.organization_id == org_id,
        )
    )
    change = result.scalar_one_or_none()

    if not change:
        raise HTTPException(status_code=404, detail="Change record not found")

    if change.status not in ["draft", "proposed"]:
        raise HTTPException(
            status_code=400, detail=f"Cannot update change in '{change.status}' status"
        )

    update_data = change_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(change, field, value)

    await db.commit()
    await db.refresh(change)

    await dependencies.audit_log(
        action="change_record.update",
        resource_type="change_record",
        resource_id=str(change.id),
        resource_name=change.change_number,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return schemas.ChangeRecordResponse(
        id=str(change.id),
        organization_id=str(change.organization_id),
        change_number=change.change_number,
        status=change.status,
        change_type=change.change_type,
        title=change.title,
        description=change.description,
        risk_level=change.risk_level,
        compliance_justification=change.compliance_justification,
        affected_devices=change.affected_devices or [],
        affected_compliance_scopes=change.affected_compliance_scopes or [],
        requested_by=str(change.requested_by) if change.requested_by else None,
        requested_at=change.requested_at,
        approved_by=str(change.approved_by) if change.approved_by else None,
        approved_at=change.approved_at,
        approval_notes=change.approval_notes,
        proposed_change_hash=change.proposed_change_hash,
        pre_change_hash=change.pre_change_hash,
        post_change_hash=change.post_change_hash,
        simulation_performed=change.simulation_performed,
        simulation_results=change.simulation_results,
        simulation_passed=change.simulation_passed,
        implemented_by=str(change.implemented_by) if change.implemented_by else None,
        implemented_at=change.implemented_at,
        implementation_evidence=change.implementation_evidence,
        verification_results=change.verification_results,
        verification_passed=change.verification_passed,
        rollback_performed=change.rollback_performed,
        rollback_at=change.rollback_at,
        rollback_reason=change.rollback_reason,
        external_ticket_id=change.external_ticket_id,
        external_ticket_url=change.external_ticket_url,
        ticket_system=change.ticket_system,
        created_at=change.created_at,
        updated_at=change.updated_at,
    )


@router.delete("/changes/{change_id}", status_code=204)
async def delete_change_record(
    change_id: str,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a change record (draft status only)"""
    from uuid import UUID
    from sqlalchemy import select
    from fastapi import HTTPException
    from app.models.models import ChangeRecord

    try:
        change_uuid = UUID(change_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid change ID format")

    org_id = UUID(current_user.organization_id)
    result = await db.execute(
        select(ChangeRecord).where(
            ChangeRecord.id == change_uuid,
            ChangeRecord.organization_id == org_id,
        )
    )
    change = result.scalar_one_or_none()

    if not change:
        raise HTTPException(status_code=404, detail="Change record not found")

    if change.status != "draft":
        raise HTTPException(
            status_code=400, detail="Can only delete change records in draft status"
        )

    await db.delete(change)
    await db.commit()

    await dependencies.audit_log(
        action="change_record.delete",
        resource_type="change_record",
        resource_id=change_id,
        resource_name=change.change_number,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return None


@router.post(
    "/changes/{change_id}/propose", response_model=schemas.ChangeRecordResponse
)
async def propose_change(
    change_id: str,
    request: schemas.ChangeProposeRequest,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit change for approval; capture proposed change hash"""
    from uuid import UUID
    from app.models.models import ChangeRecord

    try:
        change_uuid = UUID(change_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid change ID format")

    org_id = UUID(current_user.organization_id)
    result = await db.execute(
        select(ChangeRecord).where(
            ChangeRecord.id == change_uuid,
            ChangeRecord.organization_id == org_id,
        )
    )
    change = result.scalar_one_or_none()

    if not change:
        raise HTTPException(status_code=404, detail="Change record not found")

    if not can_transition(change.status, "proposed"):
        raise HTTPException(
            status_code=400, detail=f"Cannot propose change in '{change.status}' status"
        )

    if not change.affected_devices:
        raise HTTPException(
            status_code=400, detail="At least one affected device must be specified"
        )

    change.status = "proposed"
    change.proposed_change_hash = request.proposed_change_hash

    await db.commit()
    await db.refresh(change)

    await dependencies.audit_log(
        action="change_record.propose",
        resource_type="change_record",
        resource_id=str(change.id),
        resource_name=change.change_number,
        outcome="success",
        details={"proposed_change_hash": request.proposed_change_hash},
        current_user=current_user,
        db=db,
    )

    return schemas.ChangeRecordResponse(
        id=str(change.id),
        organization_id=str(change.organization_id),
        change_number=change.change_number,
        status=change.status,
        change_type=change.change_type,
        title=change.title,
        description=change.description,
        risk_level=change.risk_level,
        affected_devices=change.affected_devices or [],
        affected_compliance_scopes=change.affected_compliance_scopes or [],
        requested_by=str(change.requested_by) if change.requested_by else None,
        requested_at=change.requested_at,
        proposed_change_hash=change.proposed_change_hash,
        pre_change_hash=change.pre_change_hash,
        simulation_performed=change.simulation_performed,
        simulation_passed=change.simulation_passed,
        created_at=change.created_at,
        updated_at=change.updated_at,
    )


@router.post(
    "/changes/{change_id}/approve", response_model=schemas.ChangeRecordResponse
)
async def approve_change(
    change_id: str,
    request: schemas.ChangeApproveRequest,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Approve a proposed change (requires admin role)"""
    from uuid import UUID
    from sqlalchemy import select
    from fastapi import HTTPException
    from datetime import datetime
    from app.models.models import ChangeRecord

    if current_user.role != "admin":
        raise HTTPException(
            status_code=403, detail="Only administrators can approve changes"
        )

    try:
        change_uuid = UUID(change_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid change ID format")

    org_id = UUID(current_user.organization_id)
    result = await db.execute(
        select(ChangeRecord).where(
            ChangeRecord.id == change_uuid,
            ChangeRecord.organization_id == org_id,
        )
    )
    change = result.scalar_one_or_none()

    if not change:
        raise HTTPException(status_code=404, detail="Change record not found")

    if not can_transition(change.status, "approved"):
        raise HTTPException(
            status_code=400, detail=f"Cannot approve change in '{change.status}' status"
        )

    if change.simulation_performed and not change.simulation_passed:
        raise HTTPException(
            status_code=400, detail="Simulation must pass before approval"
        )

    change.status = "approved"
    change.approved_by = UUID(current_user.id)
    change.approved_at = datetime.utcnow()
    change.approval_notes = request.approval_notes

    await db.commit()
    await db.refresh(change)

    await dependencies.audit_log(
        action="change_record.approve",
        resource_type="change_record",
        resource_id=str(change.id),
        resource_name=change.change_number,
        outcome="success",
        details={"approval_notes": request.approval_notes},
        current_user=current_user,
        db=db,
    )

    return schemas.ChangeRecordResponse(
        id=str(change.id),
        organization_id=str(change.organization_id),
        change_number=change.change_number,
        status=change.status,
        title=change.title,
        approved_by=str(change.approved_by) if change.approved_by else None,
        approved_at=change.approved_at,
        approval_notes=change.approval_notes,
        created_at=change.created_at,
        updated_at=change.updated_at,
    )


@router.post(
    "/changes/{change_id}/implement", response_model=schemas.ChangeRecordResponse
)
async def implement_change(
    change_id: str,
    request: schemas.ChangeImplementRequest,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Implement an approved change"""
    from uuid import UUID
    from sqlalchemy import select
    from fastapi import HTTPException
    from datetime import datetime
    from app.models.models import ChangeRecord

    try:
        change_uuid = UUID(change_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid change ID format")

    org_id = UUID(current_user.organization_id)
    result = await db.execute(
        select(ChangeRecord).where(
            ChangeRecord.id == change_uuid,
            ChangeRecord.organization_id == org_id,
        )
    )
    change = result.scalar_one_or_none()

    if not change:
        raise HTTPException(status_code=404, detail="Change record not found")

    if not can_transition(change.status, "in_progress"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot implement change in '{change.status}' status",
        )

    change.status = "in_progress"
    change.implemented_by = UUID(current_user.id)
    change.implemented_at = datetime.utcnow()
    change.implementation_evidence = request.implementation_evidence
    change.post_change_hash = request.post_change_hash

    await db.commit()
    await db.refresh(change)

    await dependencies.audit_log(
        action="change_record.implement",
        resource_type="change_record",
        resource_id=str(change.id),
        resource_name=change.change_number,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return schemas.ChangeRecordResponse(
        id=str(change.id),
        organization_id=str(change.organization_id),
        change_number=change.change_number,
        status=change.status,
        implemented_by=str(change.implemented_by) if change.implemented_by else None,
        implemented_at=change.implemented_at,
        implementation_evidence=change.implementation_evidence,
        post_change_hash=change.post_change_hash,
        created_at=change.created_at,
        updated_at=change.updated_at,
    )


@router.post("/changes/{change_id}/verify", response_model=schemas.ChangeRecordResponse)
async def verify_change(
    change_id: str,
    request: schemas.ChangeVerifyRequest,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify a implemented change (requires admin role)"""
    from uuid import UUID
    from app.models.models import ChangeRecord

    if current_user.role != "admin":
        raise HTTPException(
            status_code=403, detail="Only administrators can verify changes"
        )

    try:
        change_uuid = UUID(change_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid change ID format")

    org_id = UUID(current_user.organization_id)
    result = await db.execute(
        select(ChangeRecord).where(
            ChangeRecord.id == change_uuid,
            ChangeRecord.organization_id == org_id,
        )
    )
    change = result.scalar_one_or_none()

    if not change:
        raise HTTPException(status_code=404, detail="Change record not found")

    if change.status != "in_progress":
        raise HTTPException(
            status_code=400, detail="Can only verify changes in in_progress status"
        )

    change.status = "completed"
    change.verification_results = request.verification_results
    change.verification_passed = (
        request.verification_results.get("passed", False)
        if request.verification_results
        else False
    )

    await db.commit()
    await db.refresh(change)

    await dependencies.audit_log(
        action="change_record.verify",
        resource_type="change_record",
        resource_id=str(change.id),
        resource_name=change.change_number,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return schemas.ChangeRecordResponse(
        id=str(change.id),
        organization_id=str(change.organization_id),
        change_number=change.change_number,
        status=change.status,
        verification_results=change.verification_results,
        verification_passed=change.verification_passed,
        created_at=change.created_at,
        updated_at=change.updated_at,
    )


@router.post(
    "/changes/{change_id}/rollback", response_model=schemas.ChangeRecordResponse
)
async def rollback_change(
    change_id: str,
    request: schemas.ChangeRollbackRequest,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Rollback a change (requires admin role)"""
    from uuid import UUID
    from sqlalchemy import select
    from fastapi import HTTPException
    from datetime import datetime
    from app.models.models import ChangeRecord

    if current_user.role != "admin":
        raise HTTPException(
            status_code=403, detail="Only administrators can rollback changes"
        )

    try:
        change_uuid = UUID(change_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid change ID format")

    org_id = UUID(current_user.organization_id)
    result = await db.execute(
        select(ChangeRecord).where(
            ChangeRecord.id == change_uuid,
            ChangeRecord.organization_id == org_id,
        )
    )
    change = result.scalar_one_or_none()

    if not change:
        raise HTTPException(status_code=404, detail="Change record not found")

    if not can_transition(change.status, "rolled_back"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot rollback change in '{change.status}' status",
        )

    change.status = "rolled_back"
    change.rollback_performed = True
    change.rollback_at = datetime.utcnow()
    change.rollback_reason = request.rollback_reason

    await db.commit()
    await db.refresh(change)

    await dependencies.audit_log(
        action="change_record.rollback",
        resource_type="change_record",
        resource_id=str(change.id),
        resource_name=change.change_number,
        outcome="success",
        details={"rollback_reason": request.rollback_reason},
        current_user=current_user,
        db=db,
    )

    return schemas.ChangeRecordResponse(
        id=str(change.id),
        organization_id=str(change.organization_id),
        change_number=change.change_number,
        status=change.status,
        rollback_performed=change.rollback_performed,
        rollback_at=change.rollback_at,
        rollback_reason=change.rollback_reason,
        created_at=change.created_at,
        updated_at=change.updated_at,
    )


@router.post(
    "/changes/{change_id}/sync-ticket", response_model=schemas.ChangeRecordResponse
)
async def sync_change_to_ticket(
    change_id: str,
    request: schemas.ChangeSyncTicketRequest,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sync change record to external ticketing system"""
    from uuid import UUID
    from sqlalchemy import select
    from fastapi import HTTPException
    from app.models.models import ChangeRecord, IntegrationConfig
    from app.services.ticket_sync import ticket_sync_service

    try:
        change_uuid = UUID(change_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid change ID format")

    org_id = UUID(current_user.organization_id)

    result = await db.execute(
        select(ChangeRecord).where(
            ChangeRecord.id == change_uuid,
            ChangeRecord.organization_id == org_id,
        )
    )
    change = result.scalar_one_or_none()

    if not change:
        raise HTTPException(status_code=404, detail="Change record not found")

    integ_result = await db.execute(
        select(IntegrationConfig).where(
            IntegrationConfig.organization_id == org_id,
            IntegrationConfig.integration_type == request.ticket_system,
            IntegrationConfig.is_enabled is True,
        )
    )
    integration = integ_result.scalar_one_or_none()

    if not integration:
        raise HTTPException(
            status_code=404,
            detail=f"No enabled {request.ticket_system} integration found",
        )

    try:
        if request.ticket_system == "servicenow":
            ticket_result = await ticket_sync_service.create_servicenow_ticket(
                change, integration
            )
        elif request.ticket_system == "jira":
            ticket_result = await ticket_sync_service.create_jira_ticket(
                change, integration
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported ticket system: {request.ticket_system}",
            )

        change.external_ticket_id = ticket_result.get("ticket_id") or ticket_result.get(
            "ticket_key"
        )
        change.external_ticket_url = ticket_result.get("ticket_url")
        change.ticket_system = request.ticket_system

        await db.commit()
        await db.refresh(change)

    except Exception as e:
        raise HTTPException(
            status_code=502, detail=f"Failed to create ticket: {str(e)}"
        )

    return schemas.ChangeRecordResponse(
        id=str(change.id),
        organization_id=str(change.organization_id),
        change_number=change.change_number,
        status=change.status,
        external_ticket_id=change.external_ticket_id,
        external_ticket_url=change.external_ticket_url,
        ticket_system=change.ticket_system,
        updated_at=change.updated_at,
    )


@router.post("/webhooks/change/{integration_id}")
async def change_webhook(
    integration_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    """Webhook receiver for external ticketing system approval"""
    from uuid import UUID
    from sqlalchemy import select
    from fastapi import HTTPException
    from app.models.models import IntegrationConfig, ChangeRecord

    try:
        integ_uuid = UUID(integration_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid integration ID")

    result = await db.execute(
        select(IntegrationConfig).where(IntegrationConfig.id == integ_uuid)
    )
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    if integration.integration_type == "servicenow":
        change_request_id = payload.get("sys_id") or payload.get(
            "change_request", {}
        ).get("sys_id")
        state = payload.get("state") or payload.get("change_request", {}).get("state")

        if state in ["3", "approved"]:
            cr_result = await db.execute(
                select(ChangeRecord).where(
                    ChangeRecord.external_ticket_id == change_request_id
                )
            )
            change = cr_result.scalar_one_or_none()

            if change and change.status == "proposed":
                from datetime import datetime

                change.status = "approved"
                change.approved_at = datetime.utcnow()
                change.approval_notes = "Auto-approved via ServiceNow webhook"
                await db.commit()

    elif integration.integration_type == "jira":
        issue_key = payload.get("issue", {}).get("key")
        transition = payload.get("transition", {}).get("name", "").lower()

        if "approve" in transition or "resolved" in transition:
            cr_result = await db.execute(
                select(ChangeRecord).where(ChangeRecord.external_ticket_id == issue_key)
            )
            change = cr_result.scalar_one_or_none()

            if change and change.status == "proposed":
                from datetime import datetime

                change.status = "approved"
                change.approved_at = datetime.utcnow()
                change.approval_notes = "Auto-approved via JIRA webhook"
                await db.commit()

    return {"status": "received"}


# =============================================================================
# ACL SNAPSHOTS (Compliance Vault)
# =============================================================================
@router.post(
    "/acl-snapshots",
    response_model=schemas.ACLSnapshotResponse,
    status_code=201,
)
async def create_acl_snapshot(
    snapshot_data: schemas.ACLSnapshotCreate,
    db: AsyncSession = Depends(get_db),
    agent: schemas.AgentAuth = Depends(get_agent_auth),
):
    """Create a new ACL snapshot (agent-authenticated)"""
    from app.models.models import Organization

    org_result = await db.execute(
        select(Organization).where(Organization.id == UUID(agent.organization_id))
    )
    organization = org_result.scalar_one_or_none()
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")

    snapshot = ACLSnapshot(
        organization_id=UUID(agent.organization_id),
        device_id=UUID(snapshot_data.device_id),
        content_type=snapshot_data.content_type,
        encrypted_blob=snapshot_data.encrypted_blob,
        content_hmac=snapshot_data.content_hmac,
        plaintext_size_bytes=snapshot_data.plaintext_size_bytes,
        key_id=snapshot_data.key_id,
        key_provider=snapshot_data.key_provider,
        config_hash_at_capture=snapshot_data.config_hash_at_capture,
        compliance_scope=snapshot_data.compliance_scope,
    )
    db.add(snapshot)
    await db.commit()
    await db.refresh(snapshot)

    return schemas.ACLSnapshotResponse(
        id=str(snapshot.id),
        organization_id=str(snapshot.organization_id),
        device_id=str(snapshot.device_id),
        content_type=snapshot.content_type,
        encrypted_blob=snapshot.encrypted_blob,
        content_hmac=snapshot.content_hmac,
        plaintext_size_bytes=snapshot.plaintext_size_bytes,
        key_id=snapshot.key_id,
        key_provider=snapshot.key_provider,
        encryption_algorithm=snapshot.encryption_algorithm,
        captured_at=snapshot.captured_at,
        captured_by=str(snapshot.captured_by) if snapshot.captured_by else None,
        config_hash_at_capture=snapshot.config_hash_at_capture,
        compliance_scope=snapshot.compliance_scope or [],
        created_at=snapshot.created_at,
    )


@router.get("/acl-snapshots", response_model=schemas.ACLSnapshotListResponse)
async def list_acl_snapshots(
    skip: int = 0,
    limit: int = 100,
    device_id: Optional[str] = None,
    content_type: Optional[str] = None,
    current_user: schemas.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List ACL snapshots for user's organization"""
    org_id = UUID(current_user.organization_id)

    query = select(ACLSnapshot).where(ACLSnapshot.organization_id == org_id)

    if device_id:
        query = query.where(ACLSnapshot.device_id == UUID(device_id))
    if content_type:
        query = query.where(ACLSnapshot.content_type == content_type)

    query = query.order_by(ACLSnapshot.captured_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    snapshots = result.scalars().all()

    count_query = select(ACLSnapshot).where(ACLSnapshot.organization_id == org_id)
    if device_id:
        count_query = count_query.where(ACLSnapshot.device_id == UUID(device_id))
    if content_type:
        count_query = count_query.where(ACLSnapshot.content_type == content_type)

    total_result = await db.execute(count_query)
    total = len(total_result.scalars().all())

    return schemas.ACLSnapshotListResponse(
        items=[
            schemas.ACLSnapshotResponse(
                id=str(s.id),
                organization_id=str(s.organization_id),
                device_id=str(s.device_id),
                content_type=s.content_type,
                encrypted_blob=s.encrypted_blob,
                content_hmac=s.content_hmac,
                plaintext_size_bytes=s.plaintext_size_bytes,
                key_id=s.key_id,
                key_provider=s.key_provider,
                encryption_algorithm=s.encryption_algorithm,
                captured_at=s.captured_at,
                captured_by=str(s.captured_by) if s.captured_by else None,
                config_hash_at_capture=s.config_hash_at_capture,
                compliance_scope=s.compliance_scope or [],
                created_at=s.created_at,
            )
            for s in snapshots
        ],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/acl-snapshots/{snapshot_id}", response_model=schemas.ACLSnapshotResponse)
async def get_acl_snapshot(
    snapshot_id: str,
    current_user: schemas.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific ACL snapshot"""
    try:
        snapshot_uuid = UUID(snapshot_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid snapshot ID format")

    result = await db.execute(
        select(ACLSnapshot).where(
            ACLSnapshot.id == snapshot_uuid,
            ACLSnapshot.organization_id == UUID(current_user.organization_id),
        )
    )
    snapshot = result.scalar_one_or_none()

    if not snapshot:
        raise HTTPException(status_code=404, detail="ACL snapshot not found")

    return schemas.ACLSnapshotResponse(
        id=str(snapshot.id),
        organization_id=str(snapshot.organization_id),
        device_id=str(snapshot.device_id),
        content_type=snapshot.content_type,
        encrypted_blob=snapshot.encrypted_blob,
        content_hmac=snapshot.content_hmac,
        plaintext_size_bytes=snapshot.plaintext_size_bytes,
        key_id=snapshot.key_id,
        key_provider=snapshot.key_provider,
        encryption_algorithm=snapshot.encryption_algorithm,
        captured_at=snapshot.captured_at,
        captured_by=str(snapshot.captured_by) if snapshot.captured_by else None,
        config_hash_at_capture=snapshot.config_hash_at_capture,
        compliance_scope=snapshot.compliance_scope or [],
        created_at=snapshot.created_at,
    )


@router.delete("/acl-snapshots/{snapshot_id}", status_code=204)
async def delete_acl_snapshot(
    snapshot_id: str,
    current_user: schemas.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an ACL snapshot"""
    try:
        snapshot_uuid = UUID(snapshot_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid snapshot ID format")

    result = await db.execute(
        select(ACLSnapshot).where(
            ACLSnapshot.id == snapshot_uuid,
            ACLSnapshot.organization_id == UUID(current_user.organization_id),
        )
    )
    snapshot = result.scalar_one_or_none()

    if not snapshot:
        raise HTTPException(status_code=404, detail="ACL snapshot not found")

    await db.delete(snapshot)
    await db.commit()


@router.patch(
    "/acl-snapshots/{snapshot_id}", response_model=schemas.ACLSnapshotResponse
)
async def update_acl_snapshot(
    snapshot_id: str,
    snapshot_data: schemas.ACLSnapshotUpdate,
    current_user: schemas.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an ACL snapshot (e.g., compliance_scope)"""
    try:
        snapshot_uuid = UUID(snapshot_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid snapshot ID format")

    result = await db.execute(
        select(ACLSnapshot).where(
            ACLSnapshot.id == snapshot_uuid,
            ACLSnapshot.organization_id == UUID(current_user.organization_id),
        )
    )
    snapshot = result.scalar_one_or_none()

    if not snapshot:
        raise HTTPException(status_code=404, detail="ACL snapshot not found")

    if snapshot_data.compliance_scope is not None:
        snapshot.compliance_scope = snapshot_data.compliance_scope

    await db.commit()
    await db.refresh(snapshot)

    return schemas.ACLSnapshotResponse(
        id=str(snapshot.id),
        organization_id=str(snapshot.organization_id),
        device_id=str(snapshot.device_id),
        content_type=snapshot.content_type,
        encrypted_blob=snapshot.encrypted_blob,
        content_hmac=snapshot.content_hmac,
        plaintext_size_bytes=snapshot.plaintext_size_bytes,
        key_id=snapshot.key_id,
        key_provider=snapshot.key_provider,
        encryption_algorithm=snapshot.encryption_algorithm,
        captured_at=snapshot.captured_at,
        captured_by=str(snapshot.captured_by) if snapshot.captured_by else None,
        config_hash_at_capture=snapshot.config_hash_at_capture,
        compliance_scope=snapshot.compliance_scope or [],
        created_at=snapshot.created_at,
    )


# =============================================================================
# CHANGE SIMULATION (ContainerLab)
# =============================================================================
@router.post(
    "/changes/{change_id}/simulate", response_model=schemas.ChangeSimulateResponse
)
async def trigger_simulation(
    change_id: str,
    request: schemas.ChangeSimulateRequest,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger ContainerLab simulation for a proposed change"""
    from uuid import UUID
    from sqlalchemy import select
    from app.models.models import ChangeRecord
    from datetime import datetime
    from uuid import uuid4

    try:
        change_uuid = UUID(change_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid change ID format")

    org_id = UUID(current_user.organization_id)
    result = await db.execute(
        select(ChangeRecord).where(
            ChangeRecord.id == change_uuid,
            ChangeRecord.organization_id == org_id,
        )
    )
    change = result.scalar_one_or_none()

    if not change:
        raise HTTPException(status_code=404, detail="Change record not found")

    if change.status != "proposed":
        raise HTTPException(
            status_code=400, detail="Can only simulate changes in proposed status"
        )

    simulation_id = str(uuid4())

    import redis.asyncio as redis

    redis_client = redis.from_url(settings.REDIS_URL)
    await redis_client.hset(
        f"simulation:{simulation_id}",
        mapping={
            "change_id": str(change.id),
            "organization_id": str(org_id),
            "proposed_config": request.proposed_config,
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
        },
    )
    await redis_client.expire(f"simulation:{simulation_id}", 3600)
    await redis_client.close()

    change.simulation_performed = True
    change.simulation_results = {
        "simulation_id": simulation_id,
        "status": "started",
        "started_at": datetime.utcnow().isoformat(),
    }

    await db.commit()

    await dependencies.audit_log(
        action="change_record.simulate",
        resource_type="change_record",
        resource_id=str(change.id),
        resource_name=change.change_number,
        outcome="success",
        details={"simulation_id": simulation_id},
        current_user=current_user,
        db=db,
    )

    return schemas.ChangeSimulateResponse(
        change_id=str(change.id),
        simulation_id=simulation_id,
        status="started",
    )


@router.get(
    "/changes/{change_id}/simulation-results",
    response_model=schemas.ChangeRecordResponse,
)
async def get_simulation_results(
    change_id: str,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get simulation results for a change"""
    from uuid import UUID
    from sqlalchemy import select
    from app.models.models import ChangeRecord

    try:
        change_uuid = UUID(change_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid change ID format")

    org_id = UUID(current_user.organization_id)
    result = await db.execute(
        select(ChangeRecord).where(
            ChangeRecord.id == change_uuid,
            ChangeRecord.organization_id == org_id,
        )
    )
    change = result.scalar_one_or_none()

    if not change:
        raise HTTPException(status_code=404, detail="Change record not found")

    return schemas.ChangeRecordResponse(
        id=str(change.id),
        organization_id=str(change.organization_id),
        device_id=str(change.device_id),
        change_number=change.change_number,
        title=change.title,
        description=change.description,
        proposed_config=change.proposed_config,
        current_config=change.current_config,
        status=change.status,
        risk_level=change.risk_level,
        simulation_performed=change.simulation_performed,
        simulation_results=change.simulation_results,
        simulation_passed=change.simulation_passed,
        external_ticket_id=change.external_ticket_id,
        external_ticket_url=change.external_ticket_url,
        ticket_system=change.ticket_system,
        created_at=change.created_at,
        updated_at=change.updated_at,
    )


# =============================================================================
# ML ROLE CLASSIFIER
# =============================================================================
from app.services.role_classifier import RoleClassifier

# Dependency injection for classifier (allows testing with mocks)
def get_classifier() -> RoleClassifier:
    """Get role classifier instance - stateless for rule-based, injectable for testing"""
    return RoleClassifier()


@router.post("/devices/{device_id}/classify", response_model=schemas.DeviceClassificationResponse)
async def classify_device(
    device_id: UUID,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(dependencies.get_db),
    classifier: RoleClassifier = Depends(get_classifier),
):
    """Classify device role"""
    result = await db.get(Device, device_id)
    if not result:
        raise HTTPException(status_code=404, detail="Device not found")
    
    if result.organization_id != UUID(current_user.organization_id):
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # CRITICAL: Use 'meta' column, not 'device_metadata'
    metadata = result.meta or {}
    classification = classifier.classify(metadata)
    
    old_role = result.inferred_role
    result.inferred_role = classification["inferred_role"]
    result.role_confidence = classification["confidence"]
    result.role_classified_at = classification["classified_at"]
    result.role_classifier_version = "1.0.0"
    
    await db.commit()
    await db.refresh(result)
    
    # Write AuditLog entry for classification
    audit_log = AuditLog(
        organization_id=UUID(current_user.organization_id),
        user_id=UUID(current_user.id),
        action="device.role_classified",
        resource_type="device",
        resource_id=str(device_id),
        details={
            "old_role": old_role,
            "new_role": classification["inferred_role"],
            "confidence": classification["confidence"],
            "method": classification.get("method"),
        },
    )
    db.add(audit_log)
    await db.commit()
    
    return classification


@router.get("/devices/{device_id}/classification")
async def get_device_classification(
    device_id: UUID,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(dependencies.get_db),
):
    """Get device role classification"""
    result = await db.get(Device, device_id)
    if not result:
        raise HTTPException(status_code=404, detail="Device not found")
    
    if result.organization_id != UUID(current_user.organization_id):
        raise HTTPException(status_code=403, detail="Not authorized")
    
    return {
        "inferred_role": result.inferred_role,
        "confidence": result.role_confidence,
        "classified_at": result.role_classified_at,
        "classifier_version": result.role_classifier_version,
    }


@router.post("/devices/classify-batch")
async def batch_classify_devices(
    request: schemas.BatchClassifyRequest,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(dependencies.get_db),
    classifier: RoleClassifier = Depends(get_classifier),
):
    """Batch classify multiple devices - uses bulk query to avoid N+1"""
    # Bulk query all devices in one round trip
    from sqlalchemy import select
    
    stmt = select(Device).where(
        Device.id.in_(request.device_ids),
        Device.organization_id == UUID(current_user.organization_id)
    )
    db_result = await db.execute(stmt)
    devices = {str(d.id): d for d in db_result.scalars().all()}
    
    results = []
    audit_logs = []
    
    for device_id in request.device_ids:
        device = devices.get(str(device_id))
        
        if not device:
            results.append({"device_id": str(device_id), "error": "Not found or not authorized"})
            continue
        
        # CRITICAL: Use 'meta' column, not 'device_metadata'
        metadata = device.meta or {}
        classification = classifier.classify(metadata)
        
        old_role = device.inferred_role
        device.inferred_role = classification["inferred_role"]
        device.role_confidence = classification["confidence"]
        device.role_classified_at = classification["classified_at"]
        device.role_classifier_version = "1.0.0"
        
        results.append({
            "device_id": str(device_id),
            "inferred_role": classification["inferred_role"],
            "confidence": classification["confidence"],
        })
        
        # Queue AuditLog entry
        audit_logs.append(AuditLog(
            organization_id=UUID(current_user.organization_id),
            user_id=UUID(current_user.id),
            action="device.role_classified",
            resource_type="device",
            resource_id=str(device_id),
            details={
                "old_role": old_role,
                "new_role": classification["inferred_role"],
                "confidence": classification["confidence"],
                "method": classification.get("method"),
                "batch": True,
            },
        ))
    
    await db.commit()
    
    # Bulk insert audit logs
    for audit_log in audit_logs:
        db.add(audit_log)
    await db.commit()
    
    return {"results": results}


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
            await websocket.receive_text()
            await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        manager.disconnect(websocket, discovery_id)
