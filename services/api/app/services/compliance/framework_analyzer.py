"""
FrameworkAnalyzer — maps an EvidencePackage to a ReportAnalysis.

One analyze() call per report generation. Dispatches to a framework-specific
method. Each method produces a list of ControlFindings.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.services.compliance.evidence_models import (
    ControlFinding,
    EvidencePackage,
    ReportAnalysis,
)


class FrameworkAnalyzer:
    """Maps evidence to framework control findings."""

    def analyze(self, pkg: EvidencePackage, export_document_id: str) -> ReportAnalysis:
        method = {
            "pci_dss":   self._pci_dss,
            "hipaa":     self._hipaa,
            "sox_itgc":  self._sox_itgc,
            "iso_27001": self._iso_27001,
            "fedramp":   self._fedramp,
            "soc2":      self._soc2,
            "nist_csf":  self._nist_csf,
        }.get(pkg.framework)

        if method is None:
            raise ValueError(f"Unknown framework: {pkg.framework}")

        findings = method(pkg)
        return ReportAnalysis(
            framework=pkg.framework,
            org_id=pkg.org_id,
            period_start=pkg.period_start,
            period_end=pkg.period_end,
            generated_at=datetime.now(timezone.utc),
            export_document_id=export_document_id,
            findings=findings,
            devices=pkg.devices,
            changes=pkg.changes,
            audit_events=pkg.audit_events,
            topology_paths=pkg.topology_paths,
        )

    def _pci_dss(self, pkg: EvidencePackage) -> list[ControlFinding]:
        findings = []

        insecure_devices = [
            d for d in pkg.devices
            if d.security_posture.get("telnet_enabled") or d.security_posture.get("http_enabled")
        ]
        findings.append(ControlFinding(
            control_id="PCI-DSS Req 2.2",
            description="Do not use vendor-supplied defaults and remove unnecessary services",
            status="fail" if insecure_devices else "pass",
            evidence_refs=[d.device_id for d in insecure_devices],
            notes=(
                f"{len(insecure_devices)} device(s) have telnet or HTTP enabled. "
                "Disable insecure management protocols." if insecure_devices else ""
            ),
        ))

        findings.append(ControlFinding(
            control_id="PCI-DSS Req 1.3",
            description="Prohibit direct public access between the Internet and CDE",
            status="informational",
            evidence_refs=[d.device_id for d in pkg.devices],
            notes=f"{len(pkg.topology_paths)} topology path(s) collected from Neo4j graph.",
        ))

        unapproved = [c for c in pkg.changes if not c.approved_by]
        findings.append(ControlFinding(
            control_id="PCI-DSS Req 6.4",
            description="Follow change control processes for all changes to system components",
            status="fail" if unapproved else "pass",
            evidence_refs=[c.change_number for c in unapproved],
            notes=(
                f"{len(unapproved)} change(s) completed without documented approval."
                if unapproved else
                f"All {len(pkg.changes)} change(s) have documented approval."
            ),
        ))

        no_ssh = [d for d in pkg.devices if not d.security_posture.get("ssh_enabled")]
        findings.append(ControlFinding(
            control_id="PCI-DSS Req 2.1",
            description="Use strong cryptography for non-console administrative access",
            status="fail" if no_ssh else "pass",
            evidence_refs=[d.device_id for d in no_ssh],
            notes=(
                f"{len(no_ssh)} device(s) do not have SSH enabled." if no_ssh else ""
            ),
        ))

        return findings

    def _hipaa(self, pkg: EvidencePackage) -> list[ControlFinding]:
        findings = []

        insecure = [
            d for d in pkg.devices
            if d.security_posture.get("telnet_enabled") or d.security_posture.get("http_enabled")
        ]
        findings.append(ControlFinding(
            control_id="HIPAA §164.312(e)(1)",
            description="Implement technical security measures to guard against ePHI transmission",
            status="fail" if insecure else "pass",
            evidence_refs=[d.device_id for d in insecure],
            notes=(
                f"{len(insecure)} device(s) use unencrypted management protocols."
                if insecure else ""
            ),
        ))

        findings.append(ControlFinding(
            control_id="HIPAA §164.312(b)",
            description="Implement hardware/software activity audit controls",
            status="pass" if pkg.audit_events else "informational",
            evidence_refs=[e.log_id for e in pkg.audit_events[:10]],
            notes=f"{len(pkg.audit_events)} audit log entries collected for assessment period.",
        ))

        unapproved_changes = [c for c in pkg.changes if not c.approved_by]
        findings.append(ControlFinding(
            control_id="HIPAA §164.312(a)(1)",
            description="Implement access control policies for ePHI systems",
            status="fail" if unapproved_changes else "pass",
            evidence_refs=[c.change_number for c in unapproved_changes],
            notes=(
                f"{len(unapproved_changes)} change(s) lacked required approval."
                if unapproved_changes else
                f"All {len(pkg.changes)} change(s) properly approved."
            ),
        ))

        return findings

    def _sox_itgc(self, pkg: EvidencePackage) -> list[ControlFinding]:
        findings = []

        unapproved = [c for c in pkg.changes if not c.approved_by]
        findings.append(ControlFinding(
            control_id="SOX ITGC CC7.2",
            description="Changes to infrastructure require documented approval",
            status="fail" if unapproved else "pass",
            evidence_refs=[c.change_number for c in unapproved],
            notes=(
                f"{len(unapproved)} change(s) completed without documented approval."
                if unapproved else
                f"All {len(pkg.changes)} change(s) have documented approval."
            ),
        ))

        no_hash = [c for c in pkg.changes if not c.pre_change_hash or not c.post_change_hash]
        findings.append(ControlFinding(
            control_id="SOX ITGC CC6.1",
            description="Changes have cryptographic pre/post state verification",
            status="fail" if no_hash else "pass",
            evidence_refs=[c.change_number for c in no_hash],
            notes=(
                f"{len(no_hash)} change(s) missing pre/post config hash."
                if no_hash else
                "All changes have cryptographic hash verification."
            ),
        ))

        not_simulated = [
            c for c in pkg.changes
            if c.simulation_passed is None and c.status in ("implemented", "verified")
        ]
        findings.append(ControlFinding(
            control_id="SOX ITGC CC7.1",
            description="Changes tested in simulation environment before production",
            status="informational" if not_simulated else "pass",
            evidence_refs=[c.change_number for c in not_simulated],
            notes=(
                f"{len(not_simulated)} change(s) have no simulation evidence "
                "(ContainerLab module may not be enabled)."
                if not_simulated else
                "All changes passed simulation testing."
            ),
        ))

        findings.append(ControlFinding(
            control_id="SOX ITGC CC3.2",
            description="Platform access and admin actions are logged",
            status="pass" if pkg.audit_events else "informational",
            evidence_refs=[e.log_id for e in pkg.audit_events[:5]],
            notes=f"{len(pkg.audit_events)} audit events in assessment period.",
        ))

        return findings

    def _iso_27001(self, pkg: EvidencePackage) -> list[ControlFinding]:
        findings = []

        unapproved = [c for c in pkg.changes if not c.approved_by]
        findings.append(ControlFinding(
            control_id="ISO 27001 A.12.1.2",
            description="Changes to information processing facilities shall be controlled",
            status="fail" if unapproved else "pass",
            evidence_refs=[c.change_number for c in unapproved],
            notes=(
                f"{len(unapproved)} change(s) lack documented approval."
                if unapproved else ""
            ),
        ))

        no_ssh = [d for d in pkg.devices if not d.security_posture.get("ssh_enabled")]
        findings.append(ControlFinding(
            control_id="ISO 27001 A.9.4.2",
            description="Secure log-on procedures shall be used",
            status="fail" if no_ssh else "pass",
            evidence_refs=[d.device_id for d in no_ssh],
            notes=f"{len(no_ssh)} device(s) lack SSH." if no_ssh else "",
        ))

        findings.append(ControlFinding(
            control_id="ISO 27001 A.12.4.1",
            description="Event logs recording user activities shall be produced and kept",
            status="pass" if pkg.audit_events else "informational",
            evidence_refs=[e.log_id for e in pkg.audit_events[:5]],
            notes=f"{len(pkg.audit_events)} audit events collected.",
        ))

        return findings

    def _fedramp(self, pkg: EvidencePackage) -> list[ControlFinding]:
        findings = []

        unapproved = [c for c in pkg.changes if not c.approved_by]
        findings.append(ControlFinding(
            control_id="FedRAMP CM-3",
            description="Configuration Change Control — changes are authorized and documented",
            status="fail" if unapproved else "pass",
            evidence_refs=[c.change_number for c in unapproved],
            notes=f"{len(unapproved)} unapproved change(s)." if unapproved else "",
        ))

        insecure = [d for d in pkg.devices if d.security_posture.get("telnet_enabled")]
        findings.append(ControlFinding(
            control_id="FedRAMP AC-17",
            description="Remote access uses encrypted protocols only",
            status="fail" if insecure else "pass",
            evidence_refs=[d.device_id for d in insecure],
            notes=f"{len(insecure)} device(s) have telnet enabled." if insecure else "",
        ))

        findings.append(ControlFinding(
            control_id="FedRAMP AU-2",
            description="Audit events are defined and collected",
            status="pass" if pkg.audit_events else "informational",
            evidence_refs=[e.log_id for e in pkg.audit_events[:5]],
            notes=f"{len(pkg.audit_events)} audit events in period.",
        ))

        findings.append(ControlFinding(
            control_id="FedRAMP SC-7",
            description="Boundary protection — network segmentation evidence",
            status="informational",
            evidence_refs=[d.device_id for d in pkg.devices],
            notes=f"{len(pkg.topology_paths)} topology path(s) from Neo4j graph.",
        ))

        return findings

    def _soc2(self, pkg: EvidencePackage) -> list[ControlFinding]:
        findings = []

        unapproved = [c for c in pkg.changes if not c.approved_by]
        findings.append(ControlFinding(
            control_id="SOC 2 CC8.1",
            description="Changes to infrastructure follow an authorized change management process",
            status="fail" if unapproved else "pass",
            evidence_refs=[c.change_number for c in unapproved],
            notes=f"{len(unapproved)} unapproved change(s)." if unapproved else "",
        ))

        no_ssh = [d for d in pkg.devices if not d.security_posture.get("ssh_enabled")]
        findings.append(ControlFinding(
            control_id="SOC 2 CC6.1",
            description="Logical access security measures restrict access to authorized users",
            status="fail" if no_ssh else "pass",
            evidence_refs=[d.device_id for d in no_ssh],
            notes=f"{len(no_ssh)} device(s) lack SSH." if no_ssh else "",
        ))

        findings.append(ControlFinding(
            control_id="SOC 2 CC7.2",
            description="System monitoring and audit trail in place",
            status="pass" if pkg.audit_events else "informational",
            evidence_refs=[e.log_id for e in pkg.audit_events[:5]],
            notes=f"{len(pkg.audit_events)} audit events collected.",
        ))

        return findings

    def _nist_csf(self, pkg: EvidencePackage) -> list[ControlFinding]:
        findings = []

        no_ssh = [d for d in pkg.devices if not d.security_posture.get("ssh_enabled")]
        findings.append(ControlFinding(
            control_id="NIST CSF PR.AC-1",
            description="Identities and credentials are managed for authorized users",
            status="fail" if no_ssh else "pass",
            evidence_refs=[d.device_id for d in no_ssh],
            notes=f"{len(no_ssh)} device(s) lack SSH." if no_ssh else "",
        ))

        unapproved = [c for c in pkg.changes if not c.approved_by]
        findings.append(ControlFinding(
            control_id="NIST CSF PR.IP-3",
            description="Configuration change control processes are in place",
            status="fail" if unapproved else "pass",
            evidence_refs=[c.change_number for c in unapproved],
            notes=f"{len(unapproved)} unapproved change(s)." if unapproved else "",
        ))

        findings.append(ControlFinding(
            control_id="NIST CSF DE.CM-1",
            description="Network is monitored to detect potential cybersecurity events",
            status="pass" if pkg.audit_events else "informational",
            evidence_refs=[e.log_id for e in pkg.audit_events[:5]],
            notes=f"{len(pkg.audit_events)} audit events in period.",
        ))

        findings.append(ControlFinding(
            control_id="NIST CSF PR.AC-5",
            description="Network integrity is protected via network segmentation",
            status="informational",
            evidence_refs=[d.device_id for d in pkg.devices],
            notes=f"{len(pkg.topology_paths)} topology path(s) collected.",
        ))

        return findings
