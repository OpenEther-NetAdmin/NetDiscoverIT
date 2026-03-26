"""
Data classes shared across all compliance report components.

EvidencePackage flows: EvidenceCollector → FrameworkAnalyzer
ReportAnalysis flows:  FrameworkAnalyzer → PDFRenderer / DOCXRenderer
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass
class DeviceEvidence:
    device_id: str
    hostname: str | None
    compliance_scope: list[str]
    security_posture: dict  # keys: ssh_enabled, telnet_enabled, http_enabled,
                            #       https_enabled, snmp_enabled, acl_count


@dataclass
class ChangeEvidence:
    change_number: str
    title: str
    status: Literal["draft", "proposed", "approved", "implemented", "verified", "rolled_back", "failed"]
    requested_by: str | None
    approved_by: str | None
    approved_at: datetime | None
    pre_change_hash: str | None
    post_change_hash: str | None
    simulation_passed: bool | None
    affected_compliance_scopes: list[str]


@dataclass
class AuditEvidence:
    log_id: str
    action: str        # "resource_type.verb"
    outcome: Literal["success", "failure"]
    user_id: str | None
    performed_at: datetime


@dataclass
class PathEvidence:
    source_device_id: str
    target_device_id: str
    path: list[str]    # device IDs along the Neo4j shortest path
    hop_count: int


@dataclass
class EvidencePackage:
    framework: str
    org_id: str
    period_start: datetime
    period_end: datetime
    devices: list[DeviceEvidence] = field(default_factory=list)
    changes: list[ChangeEvidence] = field(default_factory=list)
    audit_events: list[AuditEvidence] = field(default_factory=list)
    topology_paths: list[PathEvidence] = field(default_factory=list)


@dataclass
class ControlFinding:
    control_id: str
    description: str
    status: Literal["pass", "fail", "informational"]
    evidence_refs: list[str]   # device IDs, CHG-YYYY-NNNN, audit log IDs
    notes: str                 # remediation hint if fail; observation if informational


@dataclass
class ReportAnalysis:
    framework: str
    org_id: str
    period_start: datetime
    period_end: datetime
    generated_at: datetime
    export_document_id: str
    findings: list[ControlFinding] = field(default_factory=list)
    devices: list[DeviceEvidence] = field(default_factory=list)
    changes: list[ChangeEvidence] = field(default_factory=list)
    audit_events: list[AuditEvidence] = field(default_factory=list)
    topology_paths: list[PathEvidence] = field(default_factory=list)
