"""
Test script for Alembic migration workflow
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


async def test_migrations():
    """Test the Alembic migration workflow."""

    print("Testing Alembic migration workflow...")

    # Test database initialization
    try:
        from app.db.database import init_db

        await init_db()
        print("✓ Database migrations completed successfully")
    except Exception as e:
        print(f"✗ Database migration failed: {e}")
        return False

    # Test that tables exist
    try:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import text
        from app.core.config import settings

        engine = create_async_engine(settings.DATABASE_URL)
        async with engine.begin() as conn:
            # Check if organizations table exists
            result = await conn.execute(text("SELECT 1 FROM organizations LIMIT 1"))
            print("✓ Organizations table exists")

            # Check if devices table exists
            result = await conn.execute(text("SELECT 1 FROM devices LIMIT 1"))
            print("✓ Devices table exists")

            # Check if vector indexes exist
            result = await conn.execute(
                text(
                    "SELECT 1 FROM pg_indexes WHERE tablename = 'devices' AND indexname LIKE '%vector%'"
                )
            )
            indexes = result.fetchall()
            if indexes:
                print(f"✓ Vector indexes exist: {[idx[0] for idx in indexes]}")
            else:
                print("⚠ Vector indexes not found")

        return True

    except Exception as e:
        print(f"✗ Database verification failed: {e}")
        return False


if __name__ == "__main__":
    asyncio.run(test_migrations())
