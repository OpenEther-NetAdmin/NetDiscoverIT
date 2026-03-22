"""
Alert routing service

Routes alerts to configured integrations (Slack, PagerDuty, etc.)
"""

from uuid import UUID
from typing import Optional
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class AlertRouter:
    """
    Routes alert events to configured integrations.
    
    Reads notify_integration_ids from AlertRule, resolves IntegrationConfig,
    and dispatches delivery to appropriate adapter.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def route_alert(
        self,
        alert_event_id: str,
        organization_id: str,
        notify_integration_ids: list[str],
    ) -> dict:
        """
        Route an alert to all configured integrations.
        
        Args:
            alert_event_id: The alert event UUID
            organization_id: The organization UUID
            notify_integration_ids: List of IntegrationConfig UUIDs
        
        Returns:
            Summary of routing results
        """
        from app.models.models import IntegrationConfig, AlertEvent
        
        results = {
            "alert_event_id": alert_event_id,
            "deliveries_attempted": 0,
            "deliveries_succeeded": 0,
            "deliveries_failed": 0,
            "errors": [],
        }
        
        if not notify_integration_ids:
            logger.info(f"No integrations configured for alert {alert_event_id}")
            return results
        
        event_uuid = UUID(alert_event_id)
        org_uuid = UUID(organization_id)
        
        event_result = await self.db.execute(
            select(AlertEvent).where(AlertEvent.id == event_uuid)
        )
        alert_event = event_result.scalar_one_or_none()
        
        if not alert_event:
            results["errors"].append("Alert event not found")
            return results
        
        for integration_id in notify_integration_ids:
            try:
                integration_uuid = UUID(integration_id)
                
                config_result = await self.db.execute(
                    select(IntegrationConfig).where(
                        IntegrationConfig.id == integration_uuid,
                        IntegrationConfig.organization_id == org_uuid,
                        IntegrationConfig.is_enabled == True,
                    )
                )
                integration = config_result.scalar_one_or_none()
                
                if not integration:
                    results["errors"].append(f"Integration {integration_id} not found or disabled")
                    continue
                
                delivery_result = await self._deliver_to_integration(
                    integration, alert_event
                )
                
                results["deliveries_attempted"] += 1
                if delivery_result["success"]:
                    results["deliveries_succeeded"] += 1
                else:
                    results["deliveries_failed"] += 1
                    results["errors"].append(delivery_result["error"])
                
                await self._update_notification_status(
                    alert_event, integration_id, delivery_result
                )
                
            except Exception as e:
                results["deliveries_failed"] += 1
                results["errors"].append(f"Error delivering to {integration_id}: {str(e)}")
                logger.exception(f"Error routing alert {alert_event_id} to {integration_id}")
        
        await self.db.commit()
        
        return results
    
    async def _deliver_to_integration(
        self,
        integration: "IntegrationConfig",
        alert_event: "AlertEvent",
    ) -> dict:
        """
        Deliver alert to a specific integration.
        
        Args:
            integration: The IntegrationConfig
            alert_event: The AlertEvent to deliver
        
        Returns:
            Delivery result with success status and optional error
        """
        adapter_name = f"deliver_{integration.integration_type}"
        adapter = getattr(self, adapter_name, None)
        
        if not adapter:
            return {
                "success": False,
                "error": f"Unsupported integration type: {integration.integration_type}",
            }
        
        return await adapter(integration, alert_event)
    
    async def deliver_slack(
        self,
        integration: "IntegrationConfig",
        alert_event: "AlertEvent",
    ) -> dict:
        """
        Deliver alert to Slack.
        
        Args:
            integration: Slack IntegrationConfig
            alert_event: AlertEvent to deliver
        
        Returns:
            Delivery result
        """
        import requests
        from cryptography.fernet import Fernet
        from app.core.config import settings
        
        try:
            fernet = Fernet(settings.CREDENTIAL_ENCRYPTION_KEY.encode())
            
            webhook_url = fernet.decrypt(
                integration.encrypted_credentials.encode()
            ).decode()
            
            severity_emoji = {
                "info": ":information_source:",
                "low": ":large_blue_circle:",
                "medium": ":warning:",
                "high": ":red_circle:",
                "critical": ":fire:",
            }
            
            emoji = severity_emoji.get(alert_event.severity, ":bell:")
            
            payload = {
                "text": f"{emoji} *{alert_event.severity.upper()}* - {alert_event.title}",
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"{emoji} {alert_event.title}",
                        },
                    },
                    {
                        "type": "section",
                        "fields": [
                            {
                                "type": "mrkdwn",
                                "text": f"*Severity:*\n{alert_event.severity}",
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Rule:*\n{alert_event.rule_id}",
                            },
                        ],
                    },
                ],
            }
            
            if alert_event.details:
                details_text = "\n".join(
                    f"• {k}: {v}" for k, v in alert_event.details.items()
                )
                payload["blocks"].append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Details:*\n{details_text}",
                    },
                })
            
            response = requests.post(webhook_url, json=payload, timeout=10)
            
            if response.status_code == 200:
                return {"success": True}
            else:
                return {
                    "success": False,
                    "error": f"Slack API returned {response.status_code}: {response.text}",
                }
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def deliver_pagerduty(
        self,
        integration: "IntegrationConfig",
        alert_event: "AlertEvent",
    ) -> dict:
        """
        Deliver alert to PagerDuty.
        
        Args:
            integration: PagerDuty IntegrationConfig
            alert_event: AlertEvent to deliver
        
        Returns:
            Delivery result
        """
        import requests
        from cryptography.fernet import Fernet
        from app.core.config import settings
        
        try:
            fernet = Fernet(settings.CREDENTIAL_ENCRYPTION_KEY.encode())
            
            creds = fernet.decrypt(
                integration.encrypted_credentials.encode()
            ).decode()
            creds_dict = eval(creds)
            
            routing_key = creds_dict.get("routing_key")
            
            if not routing_key:
                return {"success": False, "error": "Missing routing_key"}
            
            payload = {
                "routing_key": routing_key,
                "event_action": "trigger",
                "dedup_key": str(alert_event.id),
                "payload": {
                    "summary": alert_event.title,
                    "severity": alert_event.severity,
                    "source": "NetDiscoverIT",
                    "custom_details": alert_event.details or {},
                },
            }
            
            base_url = integration.base_url or "https://events.pagerduty.com"
            response = requests.post(
                f"{base_url}/v2/enqueue",
                json=payload,
                timeout=10,
            )
            
            if response.status_code in [200, 202]:
                return {"success": True}
            else:
                return {
                    "success": False,
                    "error": f"PagerDuty API returned {response.status_code}: {response.text}",
                }
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def deliver_teams(
        self,
        integration: "IntegrationConfig",
        alert_event: "AlertEvent",
    ) -> dict:
        """
        Deliver alert to Microsoft Teams.
        
        Args:
            integration: Teams IntegrationConfig
            alert_event: AlertEvent to deliver
        
        Returns:
            Delivery result
        """
        import requests
        from cryptography.fernet import Fernet
        from app.core.config import settings
        
        try:
            fernet = Fernet(settings.CREDENTIAL_ENCRYPTION_KEY.encode())
            
            webhook_url = fernet.decrypt(
                integration.encrypted_credentials.encode()
            ).decode()
            
            severity_colors = {
                "info": "informational",
                "low": "informational",
                "medium": "warning",
                "high": "error",
                "critical": "critical",
            }
            
            color = severity_colors.get(alert_event.severity, "informational")
            
            payload = {
                "@type": "MessageCard",
                "@context": "http://schema.org/extensions",
                "themeColor": "FF0000" if alert_event.severity == "critical" else "0078D7",
                "summary": alert_event.title,
                "sections": [
                    {
                        "activityTitle": alert_event.title,
                        "facts": [
                            {"name": "Severity", "value": alert_event.severity},
                            {"name": "Rule ID", "value": str(alert_event.rule_id)},
                        ],
                    }
                ],
            }
            
            if alert_event.details:
                facts = []
                for k, v in alert_event.details.items():
                    facts.append({"name": k, "value": str(v)})
                payload["sections"][0]["facts"] = facts
            
            response = requests.post(webhook_url, json=payload, timeout=10)
            
            if response.status_code == 200:
                return {"success": True}
            else:
                return {
                    "success": False,
                    "error": f"Teams API returned {response.status_code}: {response.text}",
                }
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _update_notification_status(
        self,
        alert_event: "AlertEvent",
        integration_id: str,
        delivery_result: dict,
    ) -> None:
        """
        Update the alert event's notification status.
        
        Args:
            alert_event: The AlertEvent to update
            integration_id: The integration ID that was notified
            delivery_result: Result from the delivery attempt
        """
        from datetime import datetime, timezone
        
        notifications = alert_event.notifications_sent or []
        
        notification_record = {
            "integration_id": integration_id,
            "status": "sent" if delivery_result["success"] else "failed",
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }
        
        if not delivery_result["success"]:
            notification_record["error"] = delivery_result.get("error", "Unknown error")
        
        notifications.append(notification_record)
        alert_event.notifications_sent = notifications
