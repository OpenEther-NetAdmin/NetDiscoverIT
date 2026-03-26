"""Portal overview routes"""
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import schemas
from app.api import dependencies
from app.api.dependencies import get_db, get_current_user
from app.models.models import Device, Discovery

router = APIRouter()


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
