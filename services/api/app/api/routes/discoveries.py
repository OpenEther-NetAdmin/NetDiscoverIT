"""Discovery routes"""
from uuid import UUID
from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import schemas
from app.api import dependencies
from app.api.dependencies import get_db
from app.api.rate_limit import limiter, LIMIT_READ, LIMIT_DISCOVERY_TRIGGER
from app.models.models import Discovery
from app.core.config import settings

router = APIRouter()


@router.post("", response_model=schemas.Discovery)
@limiter.limit(LIMIT_DISCOVERY_TRIGGER)
async def trigger_discovery(request: Request, 
    discovery: schemas.DiscoveryCreate,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger a new discovery"""
    from uuid import UUID, uuid4
    import json
    import redis.asyncio as redis_async

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
        redis_client = redis_async.from_url(settings.REDIS_URL)
        job_data = {
            "discovery_id": str(discovery_id),
            "organization_id": str(org_id),
            "name": discovery.name,
            "discovery_type": discovery.discovery_type,
            "scan_profile": "standard",
        }
        await redis_client.lpush("discovery:jobs", json.dumps(job_data))
        await redis_client.aclose()
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


@router.get("", response_model=list[schemas.Discovery])
@limiter.limit(LIMIT_READ)
async def list_discoveries(
    request: Request,
    skip: int = 0,
    limit: int = 20,
    status: str | None = None,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List discoveries for current organization"""
    from uuid import UUID

    org_id = UUID(current_user.organization_id)
    query = select(Discovery).where(Discovery.organization_id == org_id)

    if status:
        query = query.where(Discovery.status == status)

    query = query.order_by(Discovery.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    discoveries = result.scalars().all()

    return [
        schemas.Discovery(
            id=str(d.id),
            organization_id=str(d.organization_id),
            name=d.name,
            discovery_type=d.discovery_type or "full",
            status=d.status,
            device_count=d.results.get("device_count", 0) if d.results else 0,
            created_at=d.created_at,
            completed_at=d.completed_at,
        )
        for d in discoveries
    ]


@router.get("/{discovery_id}", response_model=schemas.Discovery)
@limiter.limit(LIMIT_READ)
async def get_discovery(request: Request, 
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
