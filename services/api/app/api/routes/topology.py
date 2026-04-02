"""
Topology route — GET /api/v1/topology
Returns full network graph: device nodes from PostgreSQL + device-to-device
connections from Neo4j. Neo4j failure is handled gracefully (empty edges).
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import schemas
from app.api.dependencies import get_current_user, get_db
from app.api.rate_limit import limiter, LIMIT_READ
from app.db.neo4j import get_neo4j_client
from app.models.models import Device

logger = logging.getLogger(__name__)

router = APIRouter()


def _device_type(role: str | None) -> str:
    """Map device_role string to one of router|switch|firewall|server|unknown."""
    r = (role or "").lower()
    if "router" in r:
        return "router"
    if "switch" in r:
        return "switch"
    if "firewall" in r or r == "fw":
        return "firewall"
    if "server" in r:
        return "server"
    return "unknown"


@router.get("", response_model=schemas.TopologyResponse)
@limiter.limit(LIMIT_READ)
async def get_topology(request: Request, 
    current_user: schemas.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all devices for this org with their topology connections.

    Devices come from PostgreSQL (has compliance_scope, device_role, etc.).
    Edges come from Neo4j. If Neo4j is unavailable, nodes are still returned
    with an empty edges list.
    """
    org_uuid = UUID(current_user.organization_id)

    result = await db.execute(
        select(Device).where(Device.organization_id == org_uuid)
    )
    devices = result.scalars().all()

    nodes = [
        schemas.TopologyNode(
            id=str(d.id),
            hostname=d.hostname or str(d.id)[:8],
            device_type=_device_type(d.device_role),
            management_ip=str(d.ip_address) if d.ip_address else None,
            compliance_scope=list(d.compliance_scope or []),
            organization_id=str(d.organization_id),
        )
        for d in devices
    ]

    edges: list[schemas.TopologyEdge] = []
    try:
        neo4j = await get_neo4j_client()
        raw = await neo4j.get_device_connections(current_user.organization_id)
        edges = [
            schemas.TopologyEdge(source=e["source"], target=e["target"])
            for e in raw
        ]
    except Exception as e:
        logger.warning(f"Neo4j unavailable for topology: {e}")

    return schemas.TopologyResponse(
        nodes=nodes,
        edges=edges,
        node_count=len(nodes),
        edge_count=len(edges),
    )
