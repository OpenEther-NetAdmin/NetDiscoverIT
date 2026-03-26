"""
Integration config routes
"""
from uuid import UUID
from fastapi import APIRouter, HTTPException, Depends, Request
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import schemas
from app.api import dependencies
from app.api.dependencies import get_db, get_current_user

router = APIRouter()


# =============================================================================
# INTEGRATION CONFIGS
# =============================================================================
@router.get("", response_model=List[schemas.IntegrationConfigResponse])
async def list_integrations(
    request: Request,
    skip: int = 0,
    limit: int = 100,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all integrations for users organization"""
    from uuid import UUID
    from sqlalchemy import select
    from app.models.models import IntegrationConfig

    org_id = UUID(current_user.organization_id)
    result = await db.execute(
        select(IntegrationConfig)
        .where(IntegrationConfig.organization_id == org_id)
        .offset(skip)
        .limit(limit)
    )
    integrations = result.scalars().all()

    await dependencies.audit_log(
        action="integration_config.list",
        resource_type="integration_config",
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return [
        schemas.IntegrationConfigResponse(
            id=str(i.id),
            organization_id=str(i.organization_id),
            integration_type=i.integration_type,
            name=i.name,
            base_url=i.base_url,
            config=i.config or {},
            is_enabled=i.is_enabled,
            created_at=i.created_at,
            updated_at=i.updated_at,
        )
        for i in integrations
    ]


@router.get(
    "/{integration_id}", response_model=schemas.IntegrationConfigResponse
)
async def get_integration(
    request: Request,
    integration_id: str,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific integration config"""
    from uuid import UUID
    from sqlalchemy import select
    from app.models.models import IntegrationConfig

    try:
        integration_uuid = UUID(integration_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid integration ID format")

    result = await db.execute(
        select(IntegrationConfig).where(
            IntegrationConfig.id == integration_uuid,
            IntegrationConfig.organization_id == UUID(current_user.organization_id),
        )
    )
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    await dependencies.audit_log(
        action="integration_config.view",
        resource_type="integration_config",
        resource_id=integration_id,
        resource_name=integration.name,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return schemas.IntegrationConfigResponse(
        id=str(integration.id),
        organization_id=str(integration.organization_id),
        integration_type=integration.integration_type,
        name=integration.name,
        base_url=integration.base_url,
        config=integration.config or {},
        is_enabled=integration.is_enabled,
        created_at=integration.created_at,
        updated_at=integration.updated_at,
    )


@router.post(
    "", response_model=schemas.IntegrationConfigResponse, status_code=201
)
async def create_integration(
    request: Request,
    integration: schemas.IntegrationConfigCreate,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new integration config"""
    from uuid import UUID, uuid4
    from app.models.models import IntegrationConfig
    import json

    org_id = UUID(current_user.organization_id)

    result = await db.execute(
        select(IntegrationConfig).where(
            IntegrationConfig.organization_id == org_id,
            IntegrationConfig.name == integration.name,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=400, detail="Integration with this name already exists"
        )

    credentials_json = json.dumps(integration.credentials)
    encrypted_creds = None
    if integration.credentials:
        from cryptography.fernet import Fernet
        from app.core.config import settings

        fernet = Fernet(settings.CREDENTIAL_ENCRYPTION_KEY.encode())
        encrypted_creds = fernet.encrypt(credentials_json.encode()).decode()

    encrypted_webhook_secret = None
    if integration.webhook_secret:
        from cryptography.fernet import Fernet
        from app.core.config import settings

        fernet = Fernet(settings.CREDENTIAL_ENCRYPTION_KEY.encode())
        encrypted_webhook_secret = fernet.encrypt(
            integration.webhook_secret.encode()
        ).decode()

    integration_obj = IntegrationConfig(
        id=uuid4(),
        organization_id=org_id,
        integration_type=integration.integration_type.value,
        name=integration.name,
        base_url=integration.base_url,
        config=integration.config,
        encrypted_credentials=encrypted_creds,
        webhook_secret=encrypted_webhook_secret,
        is_enabled=True,
    )

    db.add(integration_obj)
    await db.commit()
    await db.refresh(integration_obj)

    await dependencies.audit_log(
        action="integration_config.create",
        resource_type="integration_config",
        resource_id=str(integration_obj.id),
        resource_name=integration_obj.name,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return schemas.IntegrationConfigResponse(
        id=str(integration_obj.id),
        organization_id=str(integration_obj.organization_id),
        integration_type=integration_obj.integration_type,
        name=integration_obj.name,
        base_url=integration_obj.base_url,
        config=integration_obj.config or {},
        is_enabled=integration_obj.is_enabled,
        created_at=integration_obj.created_at,
        updated_at=integration_obj.updated_at,
    )


@router.patch(
    "/{integration_id}", response_model=schemas.IntegrationConfigResponse
)
async def update_integration(
    request: Request,
    integration_id: str,
    integration_update: schemas.IntegrationConfigUpdate,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an integration config"""
    from uuid import UUID
    from sqlalchemy import select
    from app.models.models import IntegrationConfig
    import json

    try:
        integration_uuid = UUID(integration_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid integration ID format")

    result = await db.execute(
        select(IntegrationConfig).where(
            IntegrationConfig.id == integration_uuid,
            IntegrationConfig.organization_id == UUID(current_user.organization_id),
        )
    )
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    update_data = integration_update.model_dump(exclude_unset=True)

    if "credentials" in update_data and update_data["credentials"]:
        from cryptography.fernet import Fernet
        from app.core.config import settings

        fernet = Fernet(settings.CREDENTIAL_ENCRYPTION_KEY.encode())
        credentials_json = json.dumps(update_data["credentials"])
        integration.encrypted_credentials = fernet.encrypt(
            credentials_json.encode()
        ).decode()
        del update_data["credentials"]

    if "webhook_secret" in update_data and update_data["webhook_secret"]:
        from cryptography.fernet import Fernet
        from app.core.config import settings

        fernet = Fernet(settings.CREDENTIAL_ENCRYPTION_KEY.encode())
        integration.webhook_secret = fernet.encrypt(
            update_data["webhook_secret"].encode()
        ).decode()
        del update_data["webhook_secret"]

    for field, value in update_data.items():
        if value is not None:
            setattr(integration, field, value)

    await db.commit()
    await db.refresh(integration)

    await dependencies.audit_log(
        action="integration_config.update",
        resource_type="integration_config",
        resource_id=integration_id,
        resource_name=integration.name,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return schemas.IntegrationConfigResponse(
        id=str(integration.id),
        organization_id=str(integration.organization_id),
        integration_type=integration.integration_type,
        name=integration.name,
        base_url=integration.base_url,
        config=integration.config or {},
        is_enabled=integration.is_enabled,
        created_at=integration.created_at,
        updated_at=integration.updated_at,
    )


@router.delete("/{integration_id}", status_code=204)
async def delete_integration(
    request: Request,
    integration_id: str,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an integration config"""
    from uuid import UUID
    from sqlalchemy import select
    from app.models.models import IntegrationConfig

    try:
        integration_uuid = UUID(integration_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid integration ID format")

    result = await db.execute(
        select(IntegrationConfig).where(
            IntegrationConfig.id == integration_uuid,
            IntegrationConfig.organization_id == UUID(current_user.organization_id),
        )
    )
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    await db.delete(integration)
    await db.commit()

    await dependencies.audit_log(
        action="integration_config.delete",
        resource_type="integration_config",
        resource_id=integration_id,
        resource_name=integration.name,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return None


@router.post(
    "/{integration_id}/test",
    response_model=schemas.IntegrationConfigTestResponse,
)
async def test_integration(
    request: Request,
    integration_id: str,
    test_request: schemas.IntegrationConfigTestRequest,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Test an integration configuration"""
    from uuid import UUID
    from app.models.models import IntegrationConfig
    import json

    try:
        integration_uuid = UUID(integration_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid integration ID format")

    result = await db.execute(
        select(IntegrationConfig).where(
            IntegrationConfig.id == integration_uuid,
            IntegrationConfig.organization_id == UUID(current_user.organization_id),
        )
    )
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    credentials = None
    if integration.encrypted_credentials:
        from cryptography.fernet import Fernet
        from app.core.config import settings

        fernet = Fernet(settings.CREDENTIAL_ENCRYPTION_KEY.encode())
        try:
            creds_decrypted = fernet.decrypt(
                integration.encrypted_credentials.encode()
            ).decode()
            credentials = json.loads(creds_decrypted)
        except Exception as e:
            return schemas.IntegrationConfigTestResponse(
                success=False,
                message="Failed to decrypt credentials",
                details={"error": str(e)},
            )

    test_result = await _test_integration(
        integration, credentials, test_request.test_message
    )

    await dependencies.audit_log(
        action="integration_config.test",
        resource_type="integration_config",
        resource_id=integration_id,
        resource_name=integration.name,
        outcome="success" if test_result["success"] else "failure",
        current_user=current_user,
        db=db,
    )

    return schemas.IntegrationConfigTestResponse(
        success=test_result["success"],
        message=test_result["message"],
        details=test_result.get("details"),
    )


async def _test_integration(integration, credentials, test_message):
    """Test integration connectivity based on type"""
    import httpx

    integration_type = integration.integration_type
    base_url = integration.base_url

    try:
        if integration_type == "slack":
            if not credentials or "webhook_url" not in credentials:
                return {
                    "success": False,
                    "message": "Missing webhook_url in credentials",
                }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    credentials["webhook_url"],
                    json={"text": test_message or "Test message from NetDiscoverIT"},
                    timeout=10,
                )
                if response.status_code == 200:
                    return {"success": True, "message": "Slack webhook test successful"}
                return {
                    "success": False,
                    "message": f"Slack webhook failed: {response.status_code}",
                }

        elif integration_type == "teams":
            if not credentials or "webhook_url" not in credentials:
                return {
                    "success": False,
                    "message": "Missing webhook_url in credentials",
                }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    credentials["webhook_url"],
                    json={"text": test_message or "Test message from NetDiscoverIT"},
                    timeout=10,
                )
                if response.status_code == 200:
                    return {"success": True, "message": "Teams webhook test successful"}
                return {
                    "success": False,
                    "message": f"Teams webhook failed: {response.status_code}",
                }

        elif integration_type == "servicenow":
            if not credentials or not base_url:
                return {"success": False, "message": "Missing credentials or base_url"}

            async with httpx.AsyncClient() as client:
                auth = (
                    credentials.get("username", ""),
                    credentials.get("password", ""),
                )
                response = await client.get(
                    f"{base_url}/api/now/table/change_request",
                    auth=auth,
                    params={"sysparm_limit": 1},
                    timeout=10,
                )
                if response.status_code == 200:
                    return {
                        "success": True,
                        "message": "ServiceNow API test successful",
                    }
                return {
                    "success": False,
                    "message": f"ServiceNow API failed: {response.status_code}",
                }

        elif integration_type == "jira":
            if not credentials or not base_url:
                return {"success": False, "message": "Missing credentials or base_url"}

            async with httpx.AsyncClient() as client:
                headers = {
                    "Authorization": "Basic " + credentials.get("api_token", ""),
                    "Content-Type": "application/json",
                }
                response = await client.get(
                    f"{base_url}/rest/api/3/myself",
                    headers=headers,
                    timeout=10,
                )
                if response.status_code == 200:
                    return {"success": True, "message": "JIRA API test successful"}
                return {
                    "success": False,
                    "message": f"JIRA API failed: {response.status_code}",
                }

        elif integration_type == "pagerduty":
            if not credentials or "routing_key" not in credentials:
                return {
                    "success": False,
                    "message": "Missing routing_key in credentials",
                }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://events.pagerduty.net/v2/enqueue",
                    json={
                        "routing_key": credentials["routing_key"],
                        "event_action": "trigger",
                        "payload": {
                            "summary": test_message or "Test from NetDiscoverIT",
                            "severity": "info",
                        },
                    },
                    timeout=10,
                )
                if response.status_code in (200, 202):
                    return {"success": True, "message": "PagerDuty test successful"}
                return {
                    "success": False,
                    "message": f"PagerDuty failed: {response.status_code}",
                }

        else:
            return {
                "success": False,
                "message": f"Unsupported integration type: {integration_type}",
            }

    except Exception as e:
        return {"success": False, "message": f"Test failed: {str(e)}"}


