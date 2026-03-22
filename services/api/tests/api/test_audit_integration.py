import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

sys.path.append(str(Path(__file__).resolve().parents[2]))

import pytest

from app.api import auth, dependencies, routes
from app.api.auth import AgentCreate, UserCreate, UserLogin
from app.api.schemas import DeviceCreate, DeviceUpdate, SiteCreate, SiteUpdate, User


class DummyResult:
    def __init__(self, value):
        self._value = value

    def scalars(self):
        return self

    def all(self):
        return self._value

    def scalar_one_or_none(self):
        return self._value


def _mock_user() -> User:
    return User(
        id=str(uuid4()),
        email="test@example.com",
        organization_id=str(uuid4()),
        role="admin",
    )


@pytest.fixture
def audit_spy():
    calls = []

    async def _spy(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(**kwargs)

    return calls, _spy


@pytest.mark.asyncio
async def test_device_routes_trigger_audit_log(audit_spy):
    calls, spy = audit_spy
    user = _mock_user()
    org_id = UUID(user.organization_id)

    device = SimpleNamespace(
        id=uuid4(),
        hostname="device-1",
        ip_address="10.0.0.1",
        vendor="cisco",
        device_type="router",
        device_role="core",
        organization_id=org_id,
        created_at=None,
        updated_at=None,
    )

    created_device = SimpleNamespace(**device.__dict__)
    created_device.id = uuid4()
    created_device.hostname = "device-2"

    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()

    async def execute_side_effect(*args, **kwargs):
        query = str(args[0])
        if "WHERE devices.organization_id =" in query and "devices.id" not in query:
            return DummyResult([device])
        return DummyResult(device)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(dependencies, "audit_log", spy)
        mp.setattr(routes.dependencies, "audit_log", spy)
        db.execute = AsyncMock(side_effect=execute_side_effect)

        await routes.list_devices(current_user=user, db=db)
        await routes.get_device(str(device.id), current_user=user, db=db)

        db.execute = AsyncMock(side_effect=[DummyResult(None), DummyResult(created_device)])
        await routes.create_device(
            DeviceCreate(
                hostname=created_device.hostname,
                management_ip=created_device.ip_address,
                vendor=created_device.vendor,
                device_type=created_device.device_type,
                role=created_device.device_role,
            ),
            current_user=user,
            db=db,
        )

        db.execute = AsyncMock(side_effect=execute_side_effect)
        await routes.update_device(
            str(device.id),
            DeviceUpdate(),
            current_user=user,
            db=db,
        )
        await routes.delete_device(str(device.id), current_user=user, db=db)

    assert [call["action"] for call in calls] == [
        "device.list",
        "device.view",
        "device.create",
        "device.update",
        "device.delete",
    ]
    assert all(call["resource_type"] == "device" for call in calls)
    assert calls[1]["resource_name"] == "device-1"
    assert calls[2]["resource_name"] == "device-2"


@pytest.mark.asyncio
async def test_site_routes_trigger_audit_log(audit_spy):
    calls, spy = audit_spy
    user = _mock_user()
    org_id = UUID(user.organization_id)

    site = SimpleNamespace(
        id=uuid4(),
        name="site-1",
        description="desc",
        site_type="branch",
        location_address="addr",
        timezone="UTC",
        organization_id=org_id,
        is_active=True,
        created_at=None,
        updated_at=None,
    )

    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    db.execute = AsyncMock(return_value=DummyResult([site]))

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(dependencies, "audit_log", spy)
        mp.setattr(routes.dependencies, "audit_log", spy)

        await routes.list_sites(current_user=user, db=db)
        await routes.get_site(str(site.id), current_user=user, db=db)
        await routes.create_site(
            SiteCreate(
                name="site-2",
                description="desc",
                site_type="branch",
                location_address="addr",
                timezone="UTC",
            ),
            current_user=user,
            db=db,
        )
        await routes.update_site(
            str(site.id),
            SiteUpdate(),
            current_user=user,
            db=db,
        )
        await routes.delete_site(str(site.id), current_user=user, db=db)

    assert [call["action"] for call in calls] == [
        "site.list",
        "site.view",
        "site.create",
        "site.update",
        "site.delete",
    ]
    assert all(call["resource_type"] == "site" for call in calls)
    assert calls[1]["resource_name"] == "site-1"


@pytest.mark.asyncio
async def test_agent_routes_trigger_audit_log(audit_spy):
    calls, spy = audit_spy
    user = _mock_user()
    org_id = UUID(user.organization_id)

    agent = SimpleNamespace(
        id=uuid4(),
        name="agent-1",
        api_key_hash="hash",
        organization_id=org_id,
        site_id=None,
        agent_version="1.0",
        last_seen=None,
        is_active=True,
        capabilities={},
        created_at=None,
        updated_at=None,
    )

    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock(return_value=DummyResult(agent))

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(dependencies, "audit_log", spy)
        mp.setattr(routes.dependencies, "audit_log", spy)

        await routes.list_agents(current_user=user, db=db)
        await routes.get_agent(str(agent.id), current_user=user, db=db)
        await routes.rotate_agent_key(str(agent.id), current_user=user, db=db)
        await routes.agent_heartbeat(
            str(agent.id),
            SimpleNamespace(agent_version="1.1", capabilities={"x": True}),
            db=db,
        )

    assert [call["action"] for call in calls] == [
        "agent.list",
        "agent.view",
        "agent.rotate_key",
        "agent.heartbeat",
    ]
    assert all(call["resource_type"] == "agent" for call in calls)
    assert calls[1]["resource_name"] == "agent-1"
    assert calls[2]["resource_name"] == "agent-1"
    assert calls[3]["resource_name"] == "agent-1"
    assert calls[3]["current_user"] is None


@pytest.mark.asyncio
async def test_auth_routes_trigger_audit_log(audit_spy):
    calls, spy = audit_spy

    user = SimpleNamespace(
        id=uuid4(),
        email="login@example.com",
        hashed_password="hashed",
        organization_id=uuid4(),
        role="admin",
        is_active=True,
    )

    inactive_user = SimpleNamespace(**user.__dict__)
    inactive_user.is_active = False

    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(dependencies, "audit_log", spy)
        mp.setattr(auth.dependencies, "audit_log", spy)
        mp.setattr(auth, "verify_password", lambda password, hashed: password == "good")
        mp.setattr(auth, "create_access_token", lambda data: "access")
        mp.setattr(auth, "create_refresh_token", lambda data: "refresh")

        db.execute = AsyncMock(return_value=DummyResult(user))
        result = await auth.login(UserLogin(email="login@example.com", password="good"), db=db)
        assert result.access_token == "access"

        db.execute = AsyncMock(return_value=DummyResult(user))
        with pytest.raises(Exception):
            await auth.login(UserLogin(email="login@example.com", password="bad"), db=db)

        db.execute = AsyncMock(return_value=DummyResult(inactive_user))
        with pytest.raises(Exception):
            await auth.login(UserLogin(email="login@example.com", password="good"), db=db)

        db.execute = AsyncMock(return_value=DummyResult(None))
        await auth.register(
            UserCreate(email="new@example.com", password="pw", full_name="New User"),
            db=db,
        )

    assert [call["action"] for call in calls] == [
        "user.login",
        "user.login_failed",
        "user.login_failed",
        "user.register",
    ]
    assert all(call["resource_type"] == "user" for call in calls)
    assert calls[0]["resource_name"] == "login@example.com"
    assert calls[-1]["resource_name"] == "new@example.com"
