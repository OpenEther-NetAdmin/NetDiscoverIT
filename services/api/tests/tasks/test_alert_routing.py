"""
Tests for alert routing
"""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_alert_router_routes_to_enabled_integrations():
    """Test that alert router routes to enabled integrations only"""
    from app.services.alert_routing import AlertRouter
    
    mock_db = AsyncMock()
    
    mock_event = MagicMock()
    mock_event.id = uuid4()
    mock_event.title = "Test Alert"
    mock_event.severity = "high"
    mock_event.rule_id = uuid4()
    mock_event.details = {"device": "test"}
    mock_event.notifications_sent = []
    
    event_result = MagicMock()
    event_result.scalar_one_or_none = MagicMock(return_value=mock_event)
    
    mock_integration = MagicMock()
    mock_integration.id = uuid4()
    mock_integration.integration_type = "slack"
    mock_integration.is_enabled = True
    
    config_result = MagicMock()
    config_result.scalar_one_or_none = MagicMock(return_value=mock_integration)
    
    mock_db.execute = AsyncMock(side_effect=[
        event_result,
        config_result,
    ])
    
    router = AlertRouter(mock_db)
    
    with patch.object(router, 'deliver_slack', new_callable=AsyncMock) as mock_slack:
        mock_slack.return_value = {"success": True}
        
        results = await router.route_alert(
            alert_event_id=str(mock_event.id),
            organization_id=str(uuid4()),
            notify_integration_ids=[str(mock_integration.id)],
        )
    
    assert results["deliveries_attempted"] == 1
    assert results["deliveries_succeeded"] == 1
    assert results["deliveries_failed"] == 0


@pytest.mark.asyncio
async def test_alert_router_skips_disabled_integrations():
    """Test that alert router skips disabled integrations"""
    from app.services.alert_routing import AlertRouter
    
    mock_db = AsyncMock()
    
    mock_event = MagicMock()
    mock_event.id = uuid4()
    mock_event.notifications_sent = []
    
    event_result = MagicMock()
    event_result.scalar_one_or_none = MagicMock(return_value=mock_event)
    
    config_result = MagicMock()
    config_result.scalar_one_or_none = MagicMock(return_value=None)
    
    mock_db.execute = AsyncMock(side_effect=[
        event_result,
        config_result,
    ])
    
    router = AlertRouter(mock_db)
    
    results = await router.route_alert(
        alert_event_id=str(mock_event.id),
        organization_id=str(uuid4()),
        notify_integration_ids=[str(uuid4())],
    )
    
    assert results["deliveries_attempted"] == 0
    assert "not found or disabled" in results["errors"][0]


@pytest.mark.asyncio
async def test_alert_router_handles_empty_integrations():
    """Test that alert router handles empty integration list"""
    from app.services.alert_routing import AlertRouter
    
    mock_db = AsyncMock()
    
    router = AlertRouter(mock_db)
    
    results = await router.route_alert(
        alert_event_id=str(uuid4()),
        organization_id=str(uuid4()),
        notify_integration_ids=[],
    )
    
    assert results["deliveries_attempted"] == 0


@pytest.mark.asyncio
async def test_alert_router_unknown_integration_type():
    """Test that alert router handles unknown integration types"""
    from app.services.alert_routing import AlertRouter
    
    mock_db = AsyncMock()
    
    mock_event = MagicMock()
    mock_event.id = uuid4()
    mock_event.notifications_sent = []
    
    event_result = MagicMock()
    event_result.scalar_one_or_none = MagicMock(return_value=mock_event)
    
    mock_integration = MagicMock()
    mock_integration.id = uuid4()
    mock_integration.integration_type = "unknown_type"
    mock_integration.is_enabled = True
    
    config_result = MagicMock()
    config_result.scalar_one_or_none = MagicMock(return_value=mock_integration)
    
    mock_db.execute = AsyncMock(side_effect=[
        event_result,
        config_result,
    ])
    
    router = AlertRouter(mock_db)
    
    results = await router.route_alert(
        alert_event_id=str(mock_event.id),
        organization_id=str(uuid4()),
        notify_integration_ids=[str(mock_integration.id)],
    )
    
    assert results["deliveries_failed"] == 1
    assert "Unsupported integration type" in results["errors"][0]
