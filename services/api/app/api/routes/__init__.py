"""
API routes package.

During migration, _legacy.py holds all routes not yet split into their own module.
__init__.py re-exports `router` so main.py needs no changes.
"""
from fastapi import APIRouter
from . import health, portal, websocket, discoveries, sites
from . import devices, agents, path_visualizer
from ._legacy import router as _legacy_router

router = APIRouter()
router.include_router(health.router)
router.include_router(portal.router)
router.include_router(websocket.router, tags=["websocket"])
router.include_router(discoveries.router, prefix="/discoveries", tags=["discoveries"])
router.include_router(sites.router, prefix="/sites", tags=["sites"])
router.include_router(devices.router, prefix="/devices", tags=["devices"])
router.include_router(agents.router, tags=["agents"])
router.include_router(path_visualizer.router, tags=["path"])
router.include_router(_legacy_router)   # alerts, integrations, acl_snapshots, changes remain
