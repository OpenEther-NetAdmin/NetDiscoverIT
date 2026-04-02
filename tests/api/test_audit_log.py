import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4


@pytest.mark.asyncio
async def test_audit_log_creates_record():
    """Test that audit_log creates an AuditLog record"""
    from app.api.dependencies import audit_log
    from app.api.schemas import User
    from app.models.models import AuditLog
    
    mock_user = User(
        id=str(uuid4()),
        email="test@example.com",
        organization_id=str(uuid4()),
        role="admin",
    )
    
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    
    result = await audit_log(
        action="device.view",
        resource_type="device",
        resource_id=str(uuid4()),
        resource_name="test-device",
        current_user=mock_user,
        db=mock_db,
    )
    
    assert result is not None
    mock_db.add.assert_called_once()
    audit_entry = mock_db.add.call_args[0][0]
    assert audit_entry.action == "device.view"
    assert audit_entry.resource_type == "device"
    assert audit_entry.resource_name == "test-device"
    assert audit_entry.outcome == "success"
    assert str(audit_entry.user_id) == mock_user.id
    assert str(audit_entry.organization_id) == mock_user.organization_id
    mock_db.commit.assert_called_once()
