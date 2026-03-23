import sys
from pathlib import Path
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

sys.path.append(str(Path(__file__).resolve().parents[2]))

import pytest

from app.api import auth, dependencies, routes
from app.api.auth import UserCreate, UserLogin
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


class DummyScalarResult:
    def __init__(self, value):
        self._value = value

    def scalars(self):
        return self

    def all(self):
        return self._value

    def scalar_one_or_none(self):
        if isinstance(self._value, list):
            return self._value[0] if self._value else None
        return self._value


class ObjectListResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return self._items

    def scalar_one_or_none(self):
        return self._items[0] if self._items else None

    def one_or_none(self):
        return self.scalar_one_or_none()


class SingleObjectResult:
    def __init__(self, item):
        self._item = item

    def scalar_one_or_none(self):
        return self._item

    def scalars(self):
        return self

    def all(self):
        return [self._item] if self._item is not None else []

    def one_or_none(self):
        return self._item


class DummyScalarResult:
    def __init__(self, value):
        self._value = value

    def scalars(self):
        return self

    def all(self):
        return self._value


def _mock_user() -> User:
    return User(
        id=str(uuid4()),
        email="test@example.com",
        organization_id=str(uuid4()),
        role="admin",
    )


def _mock_device(org_id: UUID, *, device_id: UUID | None = None, hostname: str = "device-1"):
    return SimpleNamespace(
        id=device_id or uuid4(),
        hostname=hostname,
        ip_address="10.0.0.1",
        vendor="cisco",
        device_type="router",
        device_role="core",
        organization_id=org_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _mock_site(org_id: UUID, *, site_id: UUID | None = None, name: str = "site-1"):
    return SimpleNamespace(
        id=site_id or uuid4(),
        name=name,
        description="desc",
        site_type="branch",
        location_address="addr",
        timezone="UTC",
        organization_id=org_id,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _mock_agent(org_id: UUID, *, agent_id: UUID | None = None, name: str = "agent-1"):
    return SimpleNamespace(
        id=agent_id or uuid4(),
        name=name,
        api_key_hash="hash",
        organization_id=org_id,
        site_id=None,
        agent_version="1.0",
        last_seen=None,
        is_active=True,
        capabilities={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
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

    device = _mock_device(org_id)
    device.created_at = None
    device.updated_at = None
    created_device = _mock_device(org_id, hostname="device-2")
    created_device.created_at = None
    created_device.updated_at = None

    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()

    async def execute_side_effect(*args, **kwargs):
        query = str(args[0])
        if "WHERE devices.organization_id =" in query and "devices.id" not in query:
            return ObjectListResult([device])
        return SingleObjectResult(device)

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

    site = _mock_site(org_id)

    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        ObjectListResult([site]),
        SingleObjectResult(site),
        DummyResult(None),
        SingleObjectResult(site),
        SingleObjectResult(site),
    ])

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

    agent = _mock_agent(org_id)

    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        ObjectListResult([agent]),
        SingleObjectResult(agent),
        SingleObjectResult(agent),
        SingleObjectResult(agent),
    ])

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
