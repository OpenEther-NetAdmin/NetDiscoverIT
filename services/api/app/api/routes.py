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
from app.models.models import Device

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
):
    """Get a specific device"""
    # TODO: Implement database query
    raise HTTPException(status_code=404, detail="Device not found")


@router.post("/devices", response_model=schemas.Device)
async def create_device(
    device: schemas.DeviceCreate,
    current_user: schemas.User = Depends(dependencies.get_current_user),
):
    """Create a new device"""
    # TODO: Implement database insert
    return {"id": "todo", **device.model_dump()}


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
