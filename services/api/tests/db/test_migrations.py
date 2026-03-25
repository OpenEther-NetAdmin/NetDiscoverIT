import pytest

@pytest.mark.asyncio
async def test_migration_adds_role_columns():
    from app.db.database import engine
    from sqlalchemy import text
    
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'devices'"))
        columns = [row[0] for row in result.fetchall()]
        
        assert "inferred_role" in columns
        assert "role_confidence" in columns
        assert "role_classified_at" in columns
        assert "role_classifier_version" in columns
