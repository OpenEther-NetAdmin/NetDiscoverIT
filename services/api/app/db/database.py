"""
PostgreSQL Database Connection
"""

import logging
from typing import AsyncGenerator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.models import Base

logger = logging.getLogger(__name__)

# Create async engine — DATABASE_URL already returns postgresql+asyncpg:// scheme
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.APP_DEBUG,
    poolclass=NullPool,  # NullPool avoids connection reuse issues in async/serverless contexts
)

# Create session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session"""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Initialize database tables and vector indexes."""
    async with engine.begin() as conn:
        # Enable pgvector extension before creating tables
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

        # HNSW indexes for the 4 Device vector columns.
        # HNSW is preferred over IVFFlat for 768-dim embeddings: better recall (95-99%),
        # no training phase, supports live inserts, and consistent performance.
        # m=16 (graph connections per layer), ef_construction=64 (build-time quality).
        # Cosine similarity matches sentence-transformer / text-embedding output space.
        hnsw_indexes = [
            ("idx_devices_role_vector",     "role_vector"),
            ("idx_devices_topology_vector", "topology_vector"),
            ("idx_devices_security_vector", "security_vector"),
            ("idx_devices_config_vector",   "config_vector"),
        ]
        for idx_name, column in hnsw_indexes:
            await conn.execute(text(
                f"CREATE INDEX IF NOT EXISTS {idx_name} "
                f"ON devices USING hnsw ({column} vector_cosine_ops) "
                f"WITH (m = 16, ef_construction = 64)"
            ))

    logger.info("Database tables and HNSW vector indexes created")


async def close_db():
    """Close database connection"""
    await engine.dispose()
    logger.info("Database connection closed")
