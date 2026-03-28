"""
Agent routes — vector upload + agent CRUD
"""
from uuid import UUID
from fastapi import APIRouter, HTTPException, Depends
from typing import List
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import schemas
from app.api import dependencies
from app.api.dependencies import get_db, get_agent_auth
from app.models.models import LocalAgent, Device

router = APIRouter()


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


@router.get("/agents", response_model=List[schemas.AgentResponse])
async def list_agents(
    skip: int = 0,
    limit: int = 100,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all agents for user's organization"""
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
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Agent heartbeat - updates last_seen, agent_version, capabilities"""
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
    from uuid import uuid4

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
