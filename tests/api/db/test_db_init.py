import asyncio
from unittest.mock import patch, MagicMock
import pytest


@pytest.mark.asyncio
async def test_init_db_runs_migrations():
    """Test that init_db actually runs alembic migrations via run_in_executor."""
    from app.db.database import init_db

    with patch("alembic.command.upgrade") as mock_upgrade:
        with patch("alembic.config.Config", MagicMock()):
            await init_db()
            mock_upgrade.assert_called_once()


@pytest.mark.asyncio
async def test_init_db_propagates_error():
    """Test that init_db raises exception when migration fails."""
    from app.db.database import init_db

    def raise_error(cfg, rev):
        raise RuntimeError("Migration failed")

    with patch("alembic.command.upgrade", raise_error):
        with pytest.raises(RuntimeError, match="Migration failed"):
            await init_db()
