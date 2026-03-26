"""
EvidenceCollector — queries PostgreSQL + Neo4j to build an EvidencePackage.

Called once per report generation. All queries are scoped to org_id.
"""
from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy import cast, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import AuditLog, ChangeRecord, Device
from app.services.compliance.evidence_models import (
    AuditEvidence,
    ChangeEvidence,
    DeviceEvidence,
    EvidencePackage,
    PathEvidence,
)

logger = logging.getLogger(__name__)

FRAMEWORK_SCOPE_TAGS: dict[str, list[str]] = {
    "pci_dss":   ["PCI-CDE", "PCI-BOUNDARY"],
    "hipaa":     ["HIPAA-PHI"],
    "sox_itgc":  ["SOX-FINANCIAL"],
    "iso_27001": ["ISO27001"],
    "fedramp":   ["FEDRAMP-BOUNDARY"],
    "soc2":      ["SOC2"],
    "nist_csf":  ["NIST-CSF"],
}

_TOPOLOGY_FRAMEWORKS = {"pci_dss", "fedramp", "nist_csf"}


class EvidenceCollector:
    """Gathers all evidence needed for a compliance report from DB and Neo4j."""

    async def collect(
        self,
        db: AsyncSession,
        neo4j_client,
        org_id: str,
        framework: str,
        period_start: datetime,
        period_end: datetime,
        scope_override: list[str] | None = None,
    ) -> EvidencePackage:
        scope_tags = scope_override or FRAMEWORK_SCOPE_TAGS.get(framework, [])
        org_uuid = UUID(org_id)

        devices = await self._collect_devices(db, org_uuid, scope_tags)
        changes = await self._collect_changes(db, org_uuid, scope_tags, period_start, period_end)
        audit_events = await self._collect_audit(db, org_uuid, period_start, period_end)
        topology_paths = await self._collect_topology(neo4j_client, devices, framework)

        return EvidencePackage(
            framework=framework,
            org_id=org_id,
            period_start=period_start,
            period_end=period_end,
            devices=devices,
            changes=changes,
            audit_events=audit_events,
            topology_paths=topology_paths,
        )

    async def _collect_devices(
        self, db: AsyncSession, org_uuid: UUID, scope_tags: list[str]
    ) -> list[DeviceEvidence]:
        if not scope_tags:
            result = await db.execute(
                select(Device).where(Device.organization_id == org_uuid, Device.is_active == True)
            )
        else:
            tag_conditions = [
                Device.compliance_scope.cast(JSONB).contains(cast([tag], JSONB))
                for tag in scope_tags
            ]
            result = await db.execute(
                select(Device).where(
                    Device.organization_id == org_uuid,
                    Device.is_active == True,
                    or_(*tag_conditions),
                )
            )
        rows = result.scalars().all()
        return [
            DeviceEvidence(
                device_id=str(r.id),
                hostname=r.hostname,
                compliance_scope=r.compliance_scope or [],
                security_posture=r.meta or {},
            )
            for r in rows
        ]

    async def _collect_changes(
        self,
        db: AsyncSession,
        org_uuid: UUID,
        scope_tags: list[str],
        period_start: datetime,
        period_end: datetime,
    ) -> list[ChangeEvidence]:
        query = select(ChangeRecord).where(
            ChangeRecord.organization_id == org_uuid,
            ChangeRecord.requested_at >= period_start,
            ChangeRecord.requested_at <= period_end,
        )
        result = await db.execute(query)
        rows = result.scalars().all()

        out = []
        for r in rows:
            scopes = r.affected_compliance_scopes or []
            if scope_tags and not any(t in scopes for t in scope_tags):
                continue
            out.append(
                ChangeEvidence(
                    change_number=r.change_number,
                    title=r.title,
                    status=r.status,
                    requested_by=str(r.requested_by) if r.requested_by else None,
                    approved_by=str(r.approved_by) if r.approved_by else None,
                    approved_at=r.approved_at,
                    pre_change_hash=r.pre_change_hash,
                    post_change_hash=r.post_change_hash,
                    simulation_passed=r.simulation_passed,
                    affected_compliance_scopes=scopes,
                )
            )
        return out

    async def _collect_audit(
        self,
        db: AsyncSession,
        org_uuid: UUID,
        period_start: datetime,
        period_end: datetime,
    ) -> list[AuditEvidence]:
        result = await db.execute(
            select(AuditLog).where(
                AuditLog.organization_id == org_uuid,
                AuditLog.timestamp >= period_start,
                AuditLog.timestamp <= period_end,
            ).order_by(AuditLog.timestamp.desc()).limit(500)
        )
        rows = result.scalars().all()
        return [
            AuditEvidence(
                log_id=str(r.id),
                action=r.action,
                outcome=r.outcome or "success",
                user_id=str(r.user_id) if r.user_id else None,
                performed_at=r.timestamp,
            )
            for r in rows
        ]

    async def _collect_topology(
        self, neo4j_client, devices: list[DeviceEvidence], framework: str
    ) -> list[PathEvidence]:
        if framework not in _TOPOLOGY_FRAMEWORKS or not devices:
            return []
        try:
            topology = await neo4j_client.get_full_topology()
            paths = []
            for rel in topology.get("relationships", []):
                paths.append(
                    PathEvidence(
                        source_device_id=str(rel.get("source", "")),
                        target_device_id=str(rel.get("target", "")),
                        path=[str(rel.get("source", "")), str(rel.get("target", ""))],
                        hop_count=1,
                    )
                )
            return paths
        except Exception as exc:
            logger.warning("Neo4j topology unavailable for compliance report: %s", exc)
            return []
