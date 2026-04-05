"""
Test configuration and fixtures
"""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport


FIXTED_ORG_ID = "00000000-0000-0000-0000-000000000001"
FIXTED_USER_ID = "00000000-0000-0000-0000-000000000002"


@pytest.fixture(scope="session", autouse=True)
def setup_test_data():
    """Set up test organization and user in database once for all tests.
    
    Only runs if API database modules are available (skips for agent-only tests).
    """
    try:
        import asyncio
        from app.db.database import engine
        from sqlalchemy import text
    except ImportError:
        yield
        return
    
    async def _setup():
        async with engine.connect() as conn:
            await conn.execute(text(f"""
                INSERT INTO organizations (id, name, slug) 
                VALUES ('{FIXTED_ORG_ID}', 'Test Organization', 'test-org')
                ON CONFLICT (id) DO NOTHING
            """))
            await conn.execute(text(f"""
                INSERT INTO users (id, organization_id, email, hashed_password, role)
                VALUES ('{FIXTED_USER_ID}', '{FIXTED_ORG_ID}', 'test@example.com', '$2b$12$G3OWrzQS6SOkOYLsDmTsG.rlfCuXrxcT1/jJhzML6gVA7kzS4Ieuu', 'admin')
                ON CONFLICT (id) DO NOTHING
            """))
            await conn.commit()
    
    asyncio.run(_setup())
    yield


@pytest.fixture
def app():
    """Return the FastAPI application"""
    from app.main import app as fastapi_app
    return fastapi_app


@pytest.fixture
def mock_user():
    """Return a mock authenticated user"""
    from app.api.schemas import User
    return User(
        id=FIXTED_USER_ID,
        email="test@example.com",
        organization_id=FIXTED_ORG_ID,
        role="admin",
    )


@pytest.fixture
def client(app, mock_user):
    """Return a sync HTTP client with mocked authentication"""
    async def mock_get_current_user():
        return mock_user

    from app.api import dependencies
    app.dependency_overrides[dependencies.get_current_user] = mock_get_current_user

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
async def async_client(app, mock_user):
    """Return an async HTTP client with mocked authentication"""
    async def mock_get_current_user():
        return mock_user

    from app.api import dependencies
    app.dependency_overrides[dependencies.get_current_user] = mock_get_current_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
