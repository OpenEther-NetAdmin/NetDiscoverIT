"""
Alembic migration smoke tests — verify schema is applied correctly.
These tests run against the live test database in Docker.
"""
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_organizations_table_exists(db: AsyncSession):
    """organizations table must exist after migrations."""
    result = await db.execute(text("SELECT 1 FROM organizations LIMIT 1"))
    assert result is not None


@pytest.mark.asyncio
async def test_devices_table_exists(db: AsyncSession):
    """devices table must exist after migrations."""
    result = await db.execute(text("SELECT 1 FROM devices LIMIT 1"))
    assert result is not None


@pytest.mark.asyncio
async def test_vector_indexes_exist(db: AsyncSession):
    """HNSW vector indexes must exist on the devices table."""
    result = await db.execute(
        text(
            "SELECT indexname FROM pg_indexes "
            "WHERE tablename = 'devices' AND indexname LIKE '%vector%'"
        )
    )
    indexes = [row[0] for row in result.fetchall()]
    assert len(indexes) >= 1, (
        f"Expected at least 1 vector index on devices, found: {indexes}"
    )


@pytest.mark.asyncio
async def test_change_records_table_has_change_number_column(db: AsyncSession):
    """change_records table must have change_number column."""
    result = await db.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'change_records' AND column_name = 'change_number'"
        )
    )
    row = result.fetchone()
    assert row is not None, "change_number column missing from change_records table"
