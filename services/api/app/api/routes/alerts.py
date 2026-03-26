"""
Alert routes — alert rules and events
"""
from uuid import UUID
from fastapi import APIRouter, HTTPException, Depends, Request
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import schemas
from app.api import dependencies
from app.api.dependencies import get_db, get_current_user, get_agent_auth

router = APIRouter()


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


