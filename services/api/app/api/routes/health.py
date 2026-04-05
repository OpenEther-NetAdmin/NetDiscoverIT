"""Health check routes"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db.database import async_session_maker

router = APIRouter()


@router.get("/health")
async def health_check():
    """Liveness/readiness health check — verifies DB and Neo4j connectivity."""
    checks: dict[str, str] = {}

    # PostgreSQL
    try:
        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {e}"

    # Neo4j
    try:
        from app.db.neo4j import get_neo4j_client
        client = await get_neo4j_client()
        await client._driver.verify_connectivity()
        checks["neo4j"] = "ok"
    except Exception as e:
        checks["neo4j"] = f"error: {e}"

    healthy = all(v == "ok" for v in checks.values())
    body = {"status": "healthy" if healthy else "degraded", "checks": checks}

    return JSONResponse(content=body, status_code=200 if healthy else 503)
