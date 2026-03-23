"""
NetDiscoverIT API
AI-powered network discovery and self-documenting platform
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.requests import Request
from fastapi.responses import JSONResponse
import logging

from app.core.config import settings
from app.api import routes
from app.api.auth import router as auth_router

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Environment: {settings.APP_ENV}")

    # Startup - Initialize databases
    from app.db.database import init_db
    from app.db.neo4j import get_neo4j_client

    try:
        await init_db()
        logger.info("Database migrations completed successfully")
    except Exception as e:
        logger.warning(f"Database migration failed: {e}")

    try:
        neo4j = await get_neo4j_client()
        await neo4j.create_constraints()
        logger.info("Neo4j initialized")
    except Exception as e:
        logger.warning(f"Neo4j init failed: {e}")

    yield

    # Shutdown
    from app.db.database import close_db
    from app.db.neo4j import close_neo4j_client

    await close_db()
    await close_neo4j_client()

    logger.info("Shutting down application")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-powered network discovery and self-documenting platform",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Rate limiter with default limits
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.RATE_LIMIT_READ]
)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded"}
    )

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(routes.router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "healthy",
    }


@app.get("/health")
async def health():
    """Detailed health check"""
    return {"status": "healthy", "version": settings.APP_VERSION}
