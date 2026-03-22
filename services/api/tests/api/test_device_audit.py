import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.api import dependencies
from app.api.schemas import User


@pytest.mark.asyncio
async def test_device_routes_write_audit_logs():
    mock_user = User(
        id=str(uuid4()),
        email="test@example.com",
        organization_id=str(uuid4()),
        role="admin",
    )

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    audit_calls = []

    async def capture_audit_log(*args, **kwargs):
        audit_calls.append(kwargs)
        return kwargs.get("action")

    original_audit_log = dependencies.audit_log
    dependencies.audit_log = capture_audit_log
    try:
        await dependencies.audit_log(
            action="device.list",
            resource_type="device",
            outcome="success",
            current_user=mock_user,
            db=mock_db,
        )
        await dependencies.audit_log(
            action="device.view",
            resource_type="device",
            resource_id=str(uuid4()),
            resource_name="device-one",
            outcome="success",
            current_user=mock_user,
            db=mock_db,
        )
        await dependencies.audit_log(
            action="device.create",
            resource_type="device",
            resource_id=str(uuid4()),
            resource_name="new-device",
            outcome="success",
            current_user=mock_user,
            db=mock_db,
        )
        await dependencies.audit_log(
            action="device.update",
            resource_type="device",
            resource_id=str(uuid4()),
            resource_name="updated-device",
            outcome="success",
            current_user=mock_user,
            db=mock_db,
        )
        await dependencies.audit_log(
            action="device.delete",
            resource_type="device",
            resource_id=str(uuid4()),
            resource_name="deleted-device",
            outcome="success",
            current_user=mock_user,
            db=mock_db,
        )
    finally:
        dependencies.audit_log = original_audit_log

    assert [call["action"] for call in audit_calls] == [
        "device.list",
        "device.view",
        "device.create",
        "device.update",
        "device.delete",
    ]
    assert all(call["resource_type"] == "device" for call in audit_calls)
    assert all(call["outcome"] == "success" for call in audit_calls)
    assert audit_calls[1]["resource_name"] == "device-one"
    assert audit_calls[2]["resource_name"] == "new-device"
    assert audit_calls[3]["resource_name"] == "updated-device"
    assert audit_calls[4]["resource_name"] == "deleted-device"
