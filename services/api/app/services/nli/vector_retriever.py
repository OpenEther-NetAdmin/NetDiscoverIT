"""
NLI Vector Retriever

Executes pgvector cosine-distance queries to find the most relevant devices
for a given query embedding and domain. Uses raw SQL for pgvector operators.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Domain → Device vector column
DOMAIN_COLUMN_MAP: dict[str, str] = {
    "inventory": "role_vector",
    "topology": "topology_vector",
    "security": "security_vector",
    "compliance": "role_vector",
    "changes": "config_vector",
}

MAX_TOP_K = 20


@dataclass
class DeviceContext:
    device_id: str
    hostname: str
    vendor: Optional[str]
    device_type: Optional[str]
    metadata: dict
    compliance_scope: list[str]
    similarity: float
    # Enrichment — populated for changes/security domains
    recent_changes: list[dict] = field(default_factory=list)
    recent_alerts: list[dict] = field(default_factory=list)


class VectorRetriever:
    """Retrieves relevant devices from pgvector for a given domain and query embedding."""

    def _clamp_top_k(self, top_k: int) -> int:
        return max(1, min(top_k, MAX_TOP_K))

    async def retrieve(
        self,
        db: AsyncSession,
        org_id: str,
        domain: str,
        query_vec: np.ndarray,
        top_k: int = 5,
    ) -> List[DeviceContext]:
        column = DOMAIN_COLUMN_MAP.get(domain, "role_vector")
        k = self._clamp_top_k(top_k)
        vec_str = json.dumps(query_vec.tolist())

        sql = text(f"""
            SELECT id, hostname, vendor, device_type, metadata, compliance_scope,
                   1 - ({column} <=> :query_vec::vector) AS similarity
            FROM devices
            WHERE organization_id = :org_id
              AND {column} IS NOT NULL
            ORDER BY {column} <=> :query_vec::vector
            LIMIT :k
        """)  # noqa: S608 — column name comes from DOMAIN_COLUMN_MAP, not user input

        result = await db.execute(sql, {"query_vec": vec_str, "org_id": org_id, "k": k})
        rows = result.fetchall()

        if not rows:
            logger.debug("VectorRetriever: no results for domain=%s org=%s", domain, org_id)
            return []

        devices = [
            DeviceContext(
                device_id=str(row.id),
                hostname=row.hostname or str(row.id),
                vendor=row.vendor,
                device_type=row.device_type,
                metadata=row.metadata or {},
                compliance_scope=row.compliance_scope or [],
                similarity=float(row.similarity),
            )
            for row in rows
        ]

        # Domain-specific enrichment
        device_ids = [d.device_id for d in devices]
        if domain == "changes":
            await self._enrich_changes(db, devices, device_ids)
        elif domain == "security":
            await self._enrich_alerts(db, devices, device_ids)

        return devices

    async def _enrich_changes(
        self, db: AsyncSession, devices: list[DeviceContext], device_ids: list[str]
    ) -> None:
        """Attach recent ChangeRecord summaries to matched devices."""
        if not device_ids:
            return
        sql = text("""
            SELECT change_number, status, risk_level, description,
                   requested_at, affected_devices
            FROM change_records
            WHERE organization_id IN (
                SELECT organization_id FROM devices WHERE id = ANY(:ids::uuid[])
            )
            AND :ids::uuid[] && affected_devices::uuid[]
            AND requested_at >= NOW() - INTERVAL '90 days'
            ORDER BY requested_at DESC
            LIMIT 20
        """)
        try:
            result = await db.execute(sql, {"ids": device_ids})
            rows = result.fetchall()
        except Exception:
            logger.warning("VectorRetriever: change enrichment query failed", exc_info=True)
            return

        # Attach changes to relevant devices
        for row in rows:
            affected = row.affected_devices or []
            summary = {
                "change_number": row.change_number,
                "status": row.status,
                "risk_level": row.risk_level,
                "description": row.description,
                "requested_at": str(row.requested_at),
            }
            for device in devices:
                if device.device_id in [str(d) for d in affected]:
                    device.recent_changes.append(summary)

    async def _enrich_alerts(
        self, db: AsyncSession, devices: list[DeviceContext], device_ids: list[str]
    ) -> None:
        """Attach recent AlertEvent summaries to matched devices."""
        if not device_ids:
            return
        sql = text("""
            SELECT ae.device_id, ar.name, ar.rule_type, ae.severity,
                   ae.message, ae.triggered_at
            FROM alert_events ae
            JOIN alert_rules ar ON ar.id = ae.rule_id
            WHERE ae.device_id = ANY(:ids::uuid[])
            AND ae.triggered_at >= NOW() - INTERVAL '30 days'
            ORDER BY ae.triggered_at DESC
            LIMIT 30
        """)
        try:
            result = await db.execute(sql, {"ids": device_ids})
            rows = result.fetchall()
        except Exception:
            logger.warning("VectorRetriever: alert enrichment query failed", exc_info=True)
            return

        by_device: dict[str, list[dict]] = {}
        for row in rows:
            key = str(row.device_id)
            by_device.setdefault(key, []).append({
                "rule_name": row.name,
                "rule_type": row.rule_type,
                "severity": row.severity,
                "message": row.message,
                "triggered_at": str(row.triggered_at),
            })

        for device in devices:
            device.recent_alerts = by_device.get(device.device_id, [])