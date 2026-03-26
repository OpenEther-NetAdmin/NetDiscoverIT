"""Unit tests for compliance report generation (Group 8b)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest  # noqa: F401

from app.services.compliance.evidence_models import (
    AuditEvidence,
    ChangeEvidence,
    DeviceEvidence,
    EvidencePackage,
    PathEvidence,
    ControlFinding,
    ReportAnalysis,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def test_evidence_package_fields():
    pkg = EvidencePackage(
        framework="pci_dss",
        org_id="org-1",
        period_start=_utcnow(),
        period_end=_utcnow(),
        devices=[
            DeviceEvidence(
                device_id="dev-1",
                hostname="router-01",
                compliance_scope=["PCI-CDE"],
                security_posture={
                    "ssh_enabled": True,
                    "telnet_enabled": False,
                    "http_enabled": False,
                    "https_enabled": True,
                    "snmp_enabled": False,
                    "acl_count": 3,
                },
            )
        ],
        changes=[],
        audit_events=[],
        topology_paths=[],
    )
    assert pkg.framework == "pci_dss"
    assert len(pkg.devices) == 1
    assert pkg.devices[0].compliance_scope == ["PCI-CDE"]


def test_report_analysis_finding_statuses():
    finding = ControlFinding(
        control_id="PCI-DSS Req 2.1",
        description="Do not use vendor-supplied defaults",
        status="pass",
        evidence_refs=["dev-1"],
        notes="",
    )
    assert finding.status in ("pass", "fail", "informational")
