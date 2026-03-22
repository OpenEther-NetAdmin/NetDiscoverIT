import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

from app.api import dependencies
from app.api import routes
from app.api.schemas import User


class DummyResult:
    def __init__(self, value):
        self._value = value

    def scalars(self):
        return self

    def all(self):
        return self._value

    def scalar_one_or_none(self):
        return self._value


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
    mock_db.refresh = AsyncMock()
    mock_db.delete = AsyncMock()
    mock_db.execute = AsyncMock()

    device_id = str(uuid4())
    device_uuid = UUID(device_id)
    device = MagicMock()
    device.id = device_uuid
    device.hostname = "device-one"
    device.ip_address = "10.0.0.1"
    device.vendor = "cisco"
    device.device_type = "router"
    device.device_role = "core"
    device.organization_id = UUID(mock_user.organization_id)
    device.created_at = None
    device.updated_at = None

    created_device = MagicMock()
    created_device.id = UUID(str(uuid4()))
    created_device.hostname = "new-device"
    created_device.ip_address = "10.0.0.2"
    created_device.vendor = "arista"
    created_device.device_type = "switch"
    created_device.device_role = "access"
    created_device.organization_id = UUID(mock_user.organization_id)
    created_device.created_at = None
    created_device.updated_at = None

    audit_calls = []

    async def capture_audit_log(*args, **kwargs):
        audit_calls.append(kwargs)
        return kwargs.get("action")

    async def fake_execute(*args, **kwargs):
        return DummyResult(device)

    original_audit_log = dependencies.audit_log
    original_routes_audit_log = routes.dependencies.audit_log
    dependencies.audit_log = capture_audit_log
    routes.dependencies.audit_log = capture_audit_log
    mock_db.execute = AsyncMock(side_effect=fake_execute)
    try:
        await routes.list_devices(current_user=mock_user, db=mock_db)
        await routes.get_device(device_id=device_id, current_user=mock_user, db=mock_db)

        mock_db.execute = AsyncMock(side_effect=[DummyResult(None), DummyResult(device)])
        await routes.create_device(
            device=MagicMock(
                hostname=created_device.hostname,
                management_ip=created_device.ip_address,
                vendor=created_device.vendor,
                device_type=created_device.device_type,
                role=created_device.device_role,
            ),
            current_user=mock_user,
            db=mock_db,
        )

        mock_db.execute = AsyncMock(side_effect=fake_execute)
        await routes.update_device(
            device_id=device_id,
            device_update=MagicMock(model_dump=lambda exclude_unset=True: {}),
            current_user=mock_user,
            db=mock_db,
        )
        await routes.delete_device(device_id=device_id, current_user=mock_user, db=mock_db)
    finally:
        dependencies.audit_log = original_audit_log
        routes.dependencies.audit_log = original_routes_audit_log

    assert [call["action"] for call in audit_calls] == [
        "device.list",
        "device.view",
        "device.create",
        "device.update",
        "device.delete",
    ]
    assert all(call["resource_type"] == "device" for call in audit_calls)
    assert audit_calls[1]["resource_name"] == "device-one"
    assert audit_calls[0]["outcome"] == "success"
