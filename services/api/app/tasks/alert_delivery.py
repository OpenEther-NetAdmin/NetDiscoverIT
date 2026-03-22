"""
Alert delivery Celery tasks

These tasks handle delivering alerts to configured integrations.
They are designed to be called from Celery but can also be invoked directly.
"""

from typing import Optional
import logging

logger = logging.getLogger(__name__)


async def deliver_alert(
    db,
    alert_event_id: str,
    organization_id: str,
    notify_integration_ids: list[str],
) -> dict:
    """
    Deliver an alert to all configured integrations.
    
    This is the main entry point for alert delivery. It routes the alert
    to the appropriate integration adapters.
    
    Args:
        db: Database session
        alert_event_id: The alert event UUID
        organization_id: The organization UUID
        notify_integration_ids: List of IntegrationConfig UUIDs
    
    Returns:
        Summary of delivery results
    """
    from app.services.alert_routing import AlertRouter
    
    router = AlertRouter(db)
    
    results = await router.route_alert(
        alert_event_id=alert_event_id,
        organization_id=organization_id,
        notify_integration_ids=notify_integration_ids,
    )
    
    return results


async def retry_failed_deliveries(
    db,
    organization_id: Optional[str] = None,
) -> dict:
    """
    Retry delivering alerts that failed previously.
    
    Args:
        db: Database session
        organization_id: Optional organization UUID to scope retries
    
    Returns:
        Summary of retry results
    """
    from uuid import UUID
    from sqlalchemy import select
    from app.models.models import AlertEvent
    
    results = {
        "alerts_retried": 0,
        "deliveries_succeeded": 0,
        "deliveries_failed": 0,
        "errors": [],
    }
    
    query = select(AlertEvent).where(
        AlertEvent.notifications_sent.isnot(None)
    )
    
    if organization_id:
        query = query.where(AlertEvent.organization_id == UUID(organization_id))
    
    result = await db.execute(query)
    events = result.scalars().all()
    
    for event in events:
        notifications = event.notifications_sent or []
        
        failed_integrations = [
            n["integration_id"] 
            for n in notifications 
            if n.get("status") == "failed"
        ]
        
        if failed_integrations:
            try:
                delivery_result = await deliver_alert(
                    db=db,
                    alert_event_id=str(event.id),
                    organization_id=str(event.organization_id),
                    notify_integration_ids=failed_integrations,
                )
                
                results["alerts_retried"] += 1
                results["deliveries_succeeded"] += delivery_result.get("deliveries_succeeded", 0)
                results["deliveries_failed"] += delivery_result.get("deliveries_failed", 0)
                
            except Exception as e:
                results["errors"].append(f"Error retrying alert {event.id}: {str(e)}")
    
    await db.commit()
    
    return results
