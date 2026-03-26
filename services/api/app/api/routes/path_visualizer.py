"""
Path visualizer route — network path tracing
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import schemas
from app.api import dependencies
from app.api.dependencies import get_db
from app.models.models import Device

router = APIRouter()


@router.post("/path/trace", response_model=schemas.PathResult)
async def trace_path(
    path_request: schemas.PathTraceRequest,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trace path between two IPs"""
    import logging
    from uuid import UUID
    from app.db.neo4j import get_neo4j_client

    org_id = UUID(current_user.organization_id)

    result = await db.execute(
        select(Device).where(
            Device.organization_id == org_id,
            Device.ip_address == path_request.source_ip,
        )
    )
    source_device = result.scalar_one_or_none()

    result = await db.execute(
        select(Device).where(
            Device.organization_id == org_id,
            Device.ip_address == path_request.destination_ip,
        )
    )
    dest_device = result.scalar_one_or_none()

    if not source_device or not dest_device:
        return schemas.PathResult(
            path_found=False,
            hops=[],
            summary={"error": "Source or destination device not found"},
            analysis={},
            issues=[
                {
                    "type": "device_not_found",
                    "message": "One or both devices not found in database",
                }
            ],
        )

    try:
        neo4j_client = await get_neo4j_client()
        path_nodes = await neo4j_client.find_path(
            source_device.hostname, dest_device.hostname
        )

        if not path_nodes:
            return schemas.PathResult(
                path_found=False,
                hops=[],
                summary={"message": "No path found between devices"},
                analysis={},
                issues=[
                    {
                        "type": "no_path",
                        "message": "No connectivity path found in topology",
                    }
                ],
            )

        hops = []
        for i, node in enumerate(path_nodes):
            hops.append(
                schemas.PathHop(
                    hop=i + 1,
                    device={
                        "hostname": node.get("hostname"),
                        "ip_address": node.get("ip_address"),
                    },
                    interface={"name": "unknown"},
                    egress={"name": "unknown"},
                )
            )

        await dependencies.audit_log(
            action="path.trace",
            resource_type="path",
            resource_name=f"{path_request.source_ip} -> {path_request.destination_ip}",
            outcome="success",
            current_user=current_user,
            db=db,
        )

        return schemas.PathResult(
            path_found=True,
            hops=hops,
            summary={
                "total_hops": len(hops),
                "source": path_request.source_ip,
                "destination": path_request.destination_ip,
            },
            analysis={"path_length": len(hops)},
            issues=[],
        )

    except Exception as e:
        logging.error(f"Path trace error: {e}")
        return schemas.PathResult(
            path_found=False,
            hops=[],
            summary={"error": str(e)},
            analysis={},
            issues=[{"type": "trace_error", "message": "Failed to trace path"}],
        )
