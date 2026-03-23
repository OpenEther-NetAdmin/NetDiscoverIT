"""
External ticketing system integration service
Supports: ServiceNow, JIRA
"""
import httpx
from typing import Dict, Any
from app.core.config import settings


class TicketSyncService:
    """Service for syncing ChangeRecord to external ticketing systems"""
    
    async def create_servicenow_ticket(
        self,
        change_record: Any,
        integration_config: Any,
    ) -> Dict[str, str]:
        """Create ServiceNow Change Request"""
        base_url = integration_config.base_url
        credentials = self._decrypt_credentials(integration_config.encrypted_credentials)
        
        auth = (credentials.get("username", ""), credentials.get("password", ""))
        
        payload = {
            "short_description": change_record.title,
            "description": change_record.description or "",
            "category": "Network",
            "type": "normal",
            "impact": self._risk_to_impact(change_record.risk_level),
            "urgency": self._risk_to_urgency(change_record.risk_level),
            "state": "1",
            "u_change_type": change_record.change_type,
            "u_requested_by": str(change_record.requested_by),
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{base_url}/api/now/table/change_request",
                auth=auth,
                json=payload,
                timeout=30,
            )
            
            if response.status_code != 201:
                raise Exception(f"ServiceNow API error: {response.text}")
            
            data = response.json()
            result = data.get("result", {})
            
            return {
                "ticket_id": result.get("sys_id", ""),
                "ticket_number": result.get("number", ""),
                "ticket_url": f"{base_url}/change_request.do?sys_id={result.get('sys_id', '')}",
            }
    
    async def create_jira_ticket(
        self,
        change_record: Any,
        integration_config: Any,
    ) -> Dict[str, str]:
        """Create JIRA Issue"""
        base_url = integration_config.base_url
        credentials = self._decrypt_credentials(integration_config.encrypted_credentials)
        
        headers = {
            "Authorization": f"Basic {credentials.get('api_token', '')}",
            "Content-Type": "application/json",
        }
        
        project_key = integration_config.config.get("project_key", "CHANGE")
        
        payload = {
            "fields": {
                "project": {"key": project_key},
                "summary": f"[{change_record.change_number}] {change_record.title}",
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": change_record.description or "",
                                }
                            ],
                        }
                    ],
                },
                "issuetype": {"name": "Task"},
                "priority": {"name": self._risk_to_jira_priority(change_record.risk_level)},
            }
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{base_url}/rest/api/3/issue",
                headers=headers,
                json=payload,
                timeout=30,
            )
            
            if response.status_code != 201:
                raise Exception(f"JIRA API error: {response.text}")
            
            data = response.json()
            
            return {
                "ticket_id": data.get("id", ""),
                "ticket_key": data.get("key", ""),
                "ticket_url": f"{base_url}/browse/{data.get('key', '')}",
            }
    
    def _decrypt_credentials(self, encrypted_credentials: str) -> Dict:
        """Decrypt stored credentials"""
        if not encrypted_credentials:
            return {}
        
        from cryptography.fernet import Fernet
        import json
        
        fernet = Fernet(settings.CREDENTIAL_ENCRYPTION_KEY.encode())
        decrypted = fernet.decrypt(encrypted_credentials.encode()).decode()
        return json.loads(decrypted)
    
    def _risk_to_impact(self, risk_level: str) -> str:
        mapping = {"low": "2", "medium": "2", "high": "1", "critical": "1"}
        return mapping.get(risk_level, "2")
    
    def _risk_to_urgency(self, risk_level: str) -> str:
        mapping = {"low": "4", "medium": "3", "high": "2", "critical": "1"}
        return mapping.get(risk_level, "3")
    
    def _risk_to_jira_priority(self, risk_level: str) -> str:
        mapping = {"low": "Low", "medium": "Medium", "high": "High", "critical": "Highest"}
        return mapping.get(risk_level, "Medium")


ticket_sync_service = TicketSyncService()