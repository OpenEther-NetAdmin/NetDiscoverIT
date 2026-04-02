"""
API routes package — aggregates all domain-specific routers.
"""
from fastapi import APIRouter
from . import health, portal, websocket
from . import discoveries, sites
from . import devices, agents, path_visualizer
from . import alerts, integrations
from . import acl_snapshots, changes, user_org_access
from . import nli
from . import compliance_reports
from . import topology

router = APIRouter()

router.include_router(health.router)
router.include_router(portal.router)
router.include_router(websocket.router,       tags=["websocket"])
router.include_router(discoveries.router,     prefix="/discoveries",   tags=["discoveries"])
router.include_router(sites.router,           prefix="/sites",         tags=["sites"])
router.include_router(devices.router,         prefix="/devices",       tags=["devices"])
router.include_router(agents.router,                                   tags=["agents"])
router.include_router(path_visualizer.router,                          tags=["path"])
router.include_router(alerts.router,                                   tags=["alerts"])
router.include_router(integrations.router,    prefix="/integrations",  tags=["integrations"])
router.include_router(acl_snapshots.router,   prefix="/acl-snapshots", tags=["acl-snapshots"])
router.include_router(changes.router,                                  tags=["changes"])
router.include_router(user_org_access.router,   prefix="/org-access",    tags=["org-access"])
router.include_router(nli.router,             prefix="/query",         tags=["nli"])
router.include_router(compliance_reports.router, prefix="/compliance/reports", tags=["compliance"])
router.include_router(topology.router, prefix="/topology", tags=["Topology"])
