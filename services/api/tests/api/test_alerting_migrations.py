import pytest
import asyncio
from sqlalchemy import text
from app.db.database import engine


@pytest.mark.asyncio
async def test_alerting_tables_exist():
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
        table_names = [row[0] for row in result.fetchall()]
        assert "alert_rules" in table_names, f"alert_rules not found. Tables: {table_names}"
        assert "alert_events" in table_names, f"alert_events not found. Tables: {table_names}"


@pytest.mark.asyncio
async def test_alert_rules_columns():
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'alert_rules'"))
        columns = [row[0] for row in result.fetchall()]
        assert "id" in columns
        assert "organization_id" in columns
        assert "name" in columns
        assert "rule_type" in columns
        assert "is_enabled" in columns


@pytest.mark.asyncio
async def test_alert_events_columns():
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'alert_events'"))
        columns = [row[0] for row in result.fetchall()]
        assert "id" in columns
        assert "rule_id" in columns
        assert "device_id" in columns
        assert "severity" in columns
        assert "acknowledged_at" in columns
