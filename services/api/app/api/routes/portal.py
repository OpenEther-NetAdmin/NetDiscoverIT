"""Portal overview routes"""
from uuid import UUID
from typing import Literal
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import schemas
from app.api import dependencies
from app.api.dependencies import get_db, get_current_user
from app.api.rate_limit import limiter, LIMIT_READ
from app.models.models import Device, Discovery, AlertEvent, UserOrgAccess

router = APIRouter()


@router.get("/portal/overview")
@limiter.limit(LIMIT_READ)
async def portal_overview(request: Request, 
    scope: Literal["self", "msp"] = Query(
        default="self",
        description="Scope: 'self' (default) for current org only, 'msp' for aggregate across all accessible orgs",
    ),
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Return portal summary metrics.

    - scope=self (default): returns metrics for the user's own organization only.
    - scope=msp: returns aggregate metrics across all organizations the user has
      been granted access to via UserOrgAccess, plus their home org.
    """
    if scope == "msp":
        return await _msp_portal_overview(current_user, db)

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
        .order_by(Device.last_seen.desc())
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


async def _msp_portal_overview(
    current_user: schemas.User,
    db: AsyncSession,
) -> schemas.PortalOverviewMSP:
    """
    Aggregate portal metrics across the user's home org and all orgs they have
    been granted access to via UserOrgAccess.
    """
    from app.models.models import Organization

    home_org_id = UUID(current_user.organization_id)

    child_org_ids_result = await db.execute(
        select(UserOrgAccess.organization_id).where(
            UserOrgAccess.user_id == UUID(current_user.id),
        )
    )
    child_org_ids = [row[0] for row in child_org_ids_result.all()]
    all_org_ids = [home_org_id] + child_org_ids

    total_devices_result = await db.execute(
        select(Device.id).where(Device.organization_id.in_(all_org_ids))
    )
    total_devices = len(total_devices_result.scalars().all())

    active_discoveries_result = await db.execute(
        select(Discovery).where(
            Discovery.organization_id.in_(all_org_ids),
            Discovery.status == "running",
        )
    )
    active_discoveries = len(active_discoveries_result.scalars().all())

    alerts_result = await db.execute(
        select(AlertEvent).where(AlertEvent.organization_id.in_(all_org_ids))
    )
    all_alerts = alerts_result.scalars().all()
    total_alerts = len(all_alerts)
    open_alerts = len([a for a in all_alerts if a.resolved_at is None])

    child_total_devices_result = await db.execute(
        select(Device.id).where(
            Device.organization_id.in_(child_org_ids)
        )
    )
    child_total_devices = len(child_total_devices_result.scalars().all())

    child_alerts_result = await db.execute(
        select(AlertEvent).where(AlertEvent.organization_id.in_(child_org_ids))
    )
    child_alerts = child_alerts_result.scalars().all()
    child_total_alerts = len(child_alerts)
    child_open_alerts = len([a for a in child_alerts if a.resolved_at is None])

    recent_devices_result = await db.execute(
        select(Device)
        .where(Device.organization_id == home_org_id)
        .order_by(Device.last_seen.desc())
        .limit(5)
    )
    recent_devices = recent_devices_result.scalars().all()

    recent_discoveries_result = await db.execute(
        select(Discovery)
        .where(Discovery.organization_id == home_org_id)
        .order_by(Discovery.created_at.desc())
        .limit(5)
    )
    recent_discoveries = recent_discoveries_result.scalars().all()

    return schemas.PortalOverviewMSP(
        total_devices=total_devices,
        active_discoveries=active_discoveries,
        total_alerts=total_alerts,
        open_alerts=open_alerts,
        child_orgs_total_devices=child_total_devices,
        child_orgs_total_alerts=child_total_alerts,
        child_orgs_open_alerts=child_open_alerts,
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
