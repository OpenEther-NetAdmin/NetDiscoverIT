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
    mock_db.commit.assert_called_once()
