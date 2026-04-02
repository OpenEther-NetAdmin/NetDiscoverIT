"""
Tests for config drift alerting
"""

import pytest
from uuid import uuid4
from datetime import datetime, timezone, timedelta

from app.tasks.alerting import detect_config_drift


@pytest.mark.asyncio
async def test_config_drift_creates_alert_when_no_approved_change():
    """Test that config drift creates an alert when there's no approved change record"""
    from unittest.mock import AsyncMock, MagicMock
    from app.models.models import Device, AlertRule, AlertEvent
    from sqlalchemy import select
    
    device_id = str(uuid4())
    org_id = str(uuid4())
    new_config_hash = "abc123new"
    
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    
    mock_device = MagicMock()
    mock_device.id = uuid4()
    mock_device.hostname = "test-device"
    mock_device.ip_address = "10.0.0.1"
    mock_device.config_hash = "abc123old"
    mock_device.organization_id = uuid4()
    
    device_result = MagicMock()
    device_result.scalar_one_or_none = MagicMock(return_value=mock_device)
    
    mock_db.execute = AsyncMock(side_effect=[
        device_result,
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
    ])
    
    result = await detect_config_drift(
        db=mock_db,
        device_id=device_id,
        new_config_hash=new_config_hash,
        organization_id=org_id,
    )
    
    assert result is None


@pytest.mark.asyncio
async def test_config_drift_allows_approved_change():
    """Test that config drift doesn't alert when change is approved"""
    from unittest.mock import AsyncMock, MagicMock
    from app.models.models import ChangeRecord
    
    device_id = str(uuid4())
    org_id = str(uuid4())
    new_config_hash = "abc123"
    
    mock_db = AsyncMock()
    
    mock_device = MagicMock()
    mock_device.id = uuid4()
    mock_device.hostname = "test-device"
    mock_device.ip_address = "10.0.0.1"
    mock_device.config_hash = "oldhash"
    mock_device.organization_id = uuid4()
    
    mock_change_record = MagicMock()
    mock_change_record.post_change_hash = new_config_hash
    mock_change_record.status = "completed"
    mock_change_record.scheduled_window_start = None
    mock_change_record.scheduled_window_end = None
    
    device_result = MagicMock()
    device_result.scalar_one_or_none = MagicMock(return_value=mock_device)
    
    change_result = MagicMock()
    change_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[mock_change_record])))
    
    mock_db.execute = AsyncMock(side_effect=[
        device_result,
        change_result,
    ])
    
    result = await detect_config_drift(
        db=mock_db,
        device_id=device_id,
        new_config_hash=new_config_hash,
        organization_id=org_id,
    )
    
    assert result is None


@pytest.mark.asyncio
async def test_config_drift_creates_alert_for_unauthorized_change():
    """Test that config drift creates alert for unauthorized change"""
    from unittest.mock import AsyncMock, MagicMock
    
    device_id = str(uuid4())
    org_id = str(uuid4())
    new_config_hash = "unauthorized_hash"
    
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    
    mock_device = MagicMock()
    mock_device.id = uuid4()
    mock_device.hostname = "test-device"
    mock_device.ip_address = "10.0.0.1"
    mock_device.config_hash = "oldhash"
    mock_device.organization_id = uuid4()
    
    mock_rule = MagicMock()
    mock_rule.id = uuid4()
    mock_rule.severity = "high"
    mock_rule.conditions = {"grace_period_minutes": 60}
    
    device_result = MagicMock()
    device_result.scalar_one_or_none = MagicMock(return_value=mock_device)
    
    change_result = MagicMock()
    change_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    
    rule_result = MagicMock()
    rule_result.scalar_one_or_none = MagicMock(return_value=mock_rule)
    
    mock_db.execute = AsyncMock(side_effect=[
        device_result,
        change_result,
        rule_result,
    ])
    
    result = await detect_config_drift(
        db=mock_db,
        device_id=device_id,
        new_config_hash=new_config_hash,
        organization_id=org_id,
    )
    
    assert result is not None
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_config_drift_returns_none_for_unknown_device():
    """Test that config drift returns None for unknown device"""
    from unittest.mock import AsyncMock, MagicMock
    
    device_id = str(uuid4())
    org_id = str(uuid4())
    
    mock_db = AsyncMock()
    
    device_result = MagicMock()
    device_result.scalar_one_or_none = MagicMock(return_value=None)
    
    mock_db.execute = AsyncMock(return_value=device_result)
    
    result = await detect_config_drift(
        db=mock_db,
        device_id=device_id,
        new_config_hash="somehash",
        organization_id=org_id,
    )
    
    assert result is None
