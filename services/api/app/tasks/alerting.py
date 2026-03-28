"""
Alerting tasks module

This module contains functions for detecting alert conditions and creating alert events.
These functions can be called from Celery tasks or directly for testing.
"""

from uuid import UUID, uuid4
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import AlertEvent

APPROVED_CHANGE_STATUSES = ["approved", "scheduled", "in_progress", "completed"]


async def detect_config_drift(
    db: AsyncSession,
    device_id: str,
    new_config_hash: str,
    organization_id: str,
    captured_at: Optional[datetime] = None,
) -> Optional[str]:
    """
    Detect unauthorized config drift for a device.

    Compares the new config_hash against approved ChangeRecord windows.
    If no approved change covers this hash transition, creates an AlertEvent.

    Args:
        db: Database session
        device_id: The device UUID that had its config changed
        new_config_hash: The SHA-256 hash of the new configuration
        organization_id: The organization UUID
        captured_at: When the config was captured (defaults to now)

    Returns:
        The alert_event_id if an alert was created, None otherwise
    """
    from app.models.models import ChangeRecord, AlertRule, Device

    if captured_at is None:
        captured_at = datetime.now(timezone.utc)

    device_uuid = UUID(device_id)
    org_uuid = UUID(organization_id)

    result = await db.execute(
        select(Device).where(
            Device.id == device_uuid,
            Device.organization_id == org_uuid,
        )
    )
    device = result.scalar_one_or_none()

    if not device:
        return None

    previous_config_hash = device.config_hash

    change_result = await db.execute(
        select(ChangeRecord)
        .where(
            ChangeRecord.organization_id == org_uuid,
            ChangeRecord.status.in_(APPROVED_CHANGE_STATUSES),
            ChangeRecord.affected_devices.contains([device_id]),
        )
        .order_by(ChangeRecord.scheduled_window_start.desc())
    )
    change_records = change_result.scalars().all()

    authorized = False
    authorized_record = None

    for record in change_records:
        if record.post_change_hash == new_config_hash:
            if record.status == "scheduled":
                if (
                    record.scheduled_window_start
                    <= captured_at
                    <= record.scheduled_window_end
                ):
                    authorized = True
                    authorized_record = record
                    break
            else:
                authorized = True
                authorized_record = record
                break

    if not authorized:
        alert_rule_result = await db.execute(
            select(AlertRule).where(
                AlertRule.organization_id == org_uuid,
                AlertRule.rule_type == "config_drift",
                AlertRule.is_enabled == True,
            )
        )
        alert_rule = alert_rule_result.scalar_one_or_none()

        if alert_rule:
            grace_period_minutes = alert_rule.conditions.get("grace_period_minutes", 60)
            grace_period_end = captured_at.replace(tzinfo=None)

            for record in change_records:
                if record.status in ["approved", "scheduled"]:
                    if record.status == "scheduled" and record.scheduled_window_end:
                        if (
                            record.scheduled_window_end.replace(tzinfo=None)
                            > grace_period_end
                        ):
                            grace_period_end = record.scheduled_window_end.replace(
                                tzinfo=None
                            )

            grace_delta = grace_period_end - captured_at.replace(tzinfo=None)
            if grace_delta.total_seconds() / 60 < grace_period_minutes:
                alert_event = AlertEvent(
                    id=uuid4(),
                    organization_id=org_uuid,
                    rule_id=alert_rule.id,
                    device_id=device_uuid,
                    severity=alert_rule.severity,
                    title=f"Unauthorized config change: {device.hostname or device.ip_address}",
                    details={
                        "device_id": device_id,
                        "device_hostname": device.hostname,
                        "device_ip": str(device.ip_address),
                        "previous_config_hash": previous_config_hash,
                        "new_config_hash": new_config_hash,
                        "no_approved_change_record": authorized_record is None,
                        "captured_at": captured_at.isoformat() if captured_at else None,
                    },
                )

                db.add(alert_event)
                await db.commit()

                return str(alert_event.id)

    return None


async def evaluate_alert_rules(
    db: AsyncSession,
    organization_id: str,
) -> dict:
    """
    Evaluate all enabled alert rules for an organization.

    This is a placeholder for the scheduled rule evaluation task.
    In production, this would be called by Celery beat.

    Args:
        db: Database session
        organization_id: The organization UUID to evaluate rules for

    Returns:
        Summary of evaluation results
    """
    from app.models.models import AlertRule, LocalAgent, Device

    org_uuid = UUID(organization_id)

    rules_result = await db.execute(
        select(AlertRule).where(
            AlertRule.organization_id == org_uuid,
            AlertRule.is_enabled == True,
        )
    )
    rules = rules_result.scalars().all()

    results = {
        "organization_id": organization_id,
        "rules_evaluated": len(rules),
        "alerts_created": 0,
        "errors": [],
    }

    for rule in rules:
        try:
            if rule.rule_type == "agent_offline":
                threshold_minutes = rule.conditions.get("threshold_minutes", 15)
                cutoff_time = datetime.now(timezone.utc)

                agents_result = await db.execute(
                    select(LocalAgent).where(
                        LocalAgent.organization_id == org_uuid,
                        LocalAgent.is_active == True,
                    )
                )
                agents = agents_result.scalars().all()

                for agent in agents:
                    if agent.last_seen:
                        last_seen = agent.last_seen.replace(tzinfo=timezone.utc)
                        minutes_offline = (cutoff_time - last_seen).total_seconds() / 60

                        if minutes_offline > threshold_minutes:
                            alert_event = AlertEvent(
                                id=uuid4(),
                                organization_id=org_uuid,
                                rule_id=rule.id,
                                agent_id=agent.id,
                                severity=rule.severity,
                                title=f"Agent offline: {agent.name}",
                                details={
                                    "agent_id": str(agent.id),
                                    "agent_name": agent.name,
                                    "last_seen": agent.last_seen.isoformat(),
                                    "minutes_offline": round(minutes_offline, 2),
                                    "threshold_minutes": threshold_minutes,
                                },
                            )
                            db.add(alert_event)
                            results["alerts_created"] += 1

            elif rule.rule_type == "device_offline":
                threshold_minutes = rule.conditions.get("threshold_minutes", 30)
                cutoff_time = datetime.now(timezone.utc)

                devices_result = await db.execute(
                    select(Device).where(
                        Device.organization_id == org_uuid,
                        Device.is_active == True,
                    )
                )
                devices = devices_result.scalars().all()

                for device in devices:
                    if device.last_seen:
                        last_seen = device.last_seen.replace(tzinfo=timezone.utc)
                        minutes_offline = (cutoff_time - last_seen).total_seconds() / 60

                        if minutes_offline > threshold_minutes:
                            alert_event = AlertEvent(
                                id=uuid4(),
                                organization_id=org_uuid,
                                rule_id=rule.id,
                                device_id=device.id,
                                severity=rule.severity,
                                title=f"Device offline: {device.hostname or device.ip_address}",
                                details={
                                    "device_id": str(device.id),
                                    "device_hostname": device.hostname,
                                    "device_ip": str(device.ip_address),
                                    "last_seen": device.last_seen.isoformat(),
                                    "minutes_offline": round(minutes_offline, 2),
                                    "threshold_minutes": threshold_minutes,
                                },
                            )
                            db.add(alert_event)
                            results["alerts_created"] += 1

            await db.commit()

        except Exception as e:
            results["errors"].append(
                {
                    "rule_id": str(rule.id),
                    "rule_name": rule.name,
                    "error": str(e),
                }
            )

    return results
