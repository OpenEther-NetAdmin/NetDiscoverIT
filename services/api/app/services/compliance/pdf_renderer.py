"""
PDFRenderer — renders a ReportAnalysis to PDF bytes using reportlab.

Produces a professional-grade multi-section report suitable for QSA review.
"""
from __future__ import annotations

import io
from collections import Counter
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.services.compliance.evidence_models import ControlFinding, ReportAnalysis

_FRAMEWORK_LABELS = {
    "pci_dss":   "PCI-DSS v4.0",
    "hipaa":     "HIPAA Security Rule",
    "sox_itgc":  "SOX ITGC",
    "iso_27001": "ISO 27001:2022",
    "fedramp":   "FedRAMP Moderate",
    "soc2":      "SOC 2 Type II",
    "nist_csf":  "NIST Cybersecurity Framework",
}

_STATUS_COLORS = {
    "pass":          colors.HexColor("#2e7d32"),
    "fail":          colors.HexColor("#c62828"),
    "informational": colors.HexColor("#1565c0"),
}


class PDFRenderer:
    """Renders a ReportAnalysis to PDF bytes."""

    def render(self, analysis: ReportAnalysis, org_name: str = "Organization") -> bytes:
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=2.5 * cm,
            bottomMargin=2 * cm,
        )
        styles = getSampleStyleSheet()
        story = []

        story += self._cover(analysis, org_name, styles)
        story.append(PageBreak())
        story += self._executive_summary(analysis, styles)
        story.append(PageBreak())
        story += self._scope_section(analysis, styles)
        story += self._findings_section(analysis, styles)
        story += self._changes_section(analysis, styles)
        story += self._audit_section(analysis, styles)
        story += self._appendix(analysis, styles)

        doc.build(story)
        return buf.getvalue()

    def _cover(self, analysis: ReportAnalysis, org_name: str, styles) -> list:
        h1 = ParagraphStyle("Cover", parent=styles["Heading1"], alignment=TA_CENTER, fontSize=22)
        h2 = ParagraphStyle("CoverSub", parent=styles["Normal"], alignment=TA_CENTER, fontSize=13)
        label = _FRAMEWORK_LABELS.get(analysis.framework, analysis.framework.upper())
        period = (
            f"{analysis.period_start.strftime('%Y-%m-%d')} — "
            f"{analysis.period_end.strftime('%Y-%m-%d')}"
        )
        return [
            Spacer(1, 4 * cm),
            Paragraph(f"{org_name}", h1),
            Spacer(1, 0.5 * cm),
            Paragraph(f"{label} Compliance Report", h1),
            Spacer(1, 1 * cm),
            Paragraph(f"Assessment Period: {period}", h2),
            Paragraph(f"Generated: {analysis.generated_at.strftime('%Y-%m-%d %H:%M UTC')}", h2),
            Spacer(1, 0.5 * cm),
            Paragraph(f"CONFIDENTIAL — RESTRICTED DISTRIBUTION", h2),
        ]

    def _executive_summary(self, analysis: ReportAnalysis, styles) -> list:
        passed = sum(1 for f in analysis.findings if f.status == "pass")
        failed = sum(1 for f in analysis.findings if f.status == "fail")
        info   = sum(1 for f in analysis.findings if f.status == "informational")
        rows = [
            ["Controls Assessed", str(len(analysis.findings))],
            ["PASS",              str(passed)],
            ["FAIL",              str(failed)],
            ["INFORMATIONAL",     str(info)],
            ["In-Scope Devices",  str(len(analysis.devices))],
            ["Changes Reviewed",  str(len(analysis.changes))],
        ]
        tbl = Table(rows, colWidths=[8 * cm, 4 * cm])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#37474f")),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("FONTNAME",   (0, 0), (-1, -1), "Helvetica"),
            ("GRID",       (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f5f5f5"), colors.white]),
        ]))
        return [
            Paragraph("Executive Summary", styles["Heading1"]),
            HRFlowable(width="100%"),
            Spacer(1, 0.3 * cm),
            tbl,
            Spacer(1, 0.5 * cm),
        ]

    def _scope_section(self, analysis: ReportAnalysis, styles) -> list:
        out = [Paragraph("Scope — In-Scope Devices", styles["Heading2"]), HRFlowable(width="100%"), Spacer(1, 0.3 * cm)]
        if not analysis.devices:
            out.append(Paragraph("No in-scope devices found for this framework.", styles["Normal"]))
            return out
        header = ["Hostname", "Device ID", "Compliance Scope"]
        rows = [header] + [
            [
                d.hostname or "(unknown)",
                d.device_id[:8] + "...",
                ", ".join(d.compliance_scope),
            ]
            for d in analysis.devices
        ]
        tbl = Table(rows, colWidths=[5 * cm, 4 * cm, 7 * cm])
        tbl.setStyle(TableStyle([
            ("BACKGROUND",  (0, 0), (-1, 0), colors.HexColor("#37474f")),
            ("TEXTCOLOR",   (0, 0), (-1, 0), colors.white),
            ("FONTNAME",    (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE",    (0, 0), (-1, -1), 9),
            ("GRID",        (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f5f5f5"), colors.white]),
        ]))
        out += [tbl, Spacer(1, 0.5 * cm)]
        return out

    def _findings_section(self, analysis: ReportAnalysis, styles) -> list:
        out = [Paragraph("Control Findings", styles["Heading2"]), HRFlowable(width="100%"), Spacer(1, 0.3 * cm)]
        for finding in analysis.findings:
            color = _STATUS_COLORS.get(finding.status, colors.black)
            status_style = ParagraphStyle(
                "Status", parent=styles["Normal"], textColor=color, fontName="Helvetica-Bold"
            )
            out.append(Paragraph(f"[{finding.status.upper()}] {finding.control_id}", status_style))
            out.append(Paragraph(finding.description, styles["Normal"]))
            if finding.notes:
                out.append(Paragraph(f"<i>{finding.notes}</i>", styles["Normal"]))
            if finding.evidence_refs:
                refs = ", ".join(finding.evidence_refs[:5])
                if len(finding.evidence_refs) > 5:
                    refs += f" (+{len(finding.evidence_refs) - 5} more)"
                out.append(Paragraph(f"Evidence: {refs}", styles["Normal"]))
            out.append(Spacer(1, 0.3 * cm))
        return out

    def _changes_section(self, analysis: ReportAnalysis, styles) -> list:
        if not analysis.changes:
            return []
        out = [Paragraph("Change Management Evidence", styles["Heading2"]), HRFlowable(width="100%"), Spacer(1, 0.3 * cm)]
        header = ["CHG #", "Title", "Approved By", "Approved At", "Sim", "Status"]
        rows = [header]
        for c in analysis.changes:
            rows.append([
                c.change_number,
                (c.title[:40] + "...") if len(c.title) > 40 else c.title,
                c.approved_by[:8] + "..." if c.approved_by else "—",
                c.approved_at.strftime("%Y-%m-%d") if c.approved_at else "—",
                "✓" if c.simulation_passed else ("—" if c.simulation_passed is None else "✗"),
                c.status,
            ])
        col_w = [2.5 * cm, 5 * cm, 2.5 * cm, 2.5 * cm, 1 * cm, 2.5 * cm]
        tbl = Table(rows, colWidths=col_w)
        tbl.setStyle(TableStyle([
            ("BACKGROUND",  (0, 0), (-1, 0), colors.HexColor("#37474f")),
            ("TEXTCOLOR",   (0, 0), (-1, 0), colors.white),
            ("FONTNAME",    (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE",    (0, 0), (-1, -1), 8),
            ("GRID",        (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f5f5f5"), colors.white]),
        ]))
        out += [tbl, Spacer(1, 0.5 * cm)]
        return out

    def _audit_section(self, analysis: ReportAnalysis, styles) -> list:
        if not analysis.audit_events:
            return []
        out = [Paragraph("Audit Trail Summary", styles["Heading2"]), HRFlowable(width="100%"), Spacer(1, 0.3 * cm)]
        out.append(Paragraph(
            f"{len(analysis.audit_events)} audit events recorded in assessment period.",
            styles["Normal"],
        ))
        from collections import Counter
        counts = Counter(e.action for e in analysis.audit_events)
        rows = [["Action", "Count"]] + [[a, str(c)] for a, c in counts.most_common(10)]
        tbl = Table(rows, colWidths=[10 * cm, 3 * cm])
        tbl.setStyle(TableStyle([
            ("BACKGROUND",  (0, 0), (-1, 0), colors.HexColor("#37474f")),
            ("TEXTCOLOR",   (0, 0), (-1, 0), colors.white),
            ("FONTNAME",    (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE",    (0, 0), (-1, -1), 9),
            ("GRID",        (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f5f5f5"), colors.white]),
        ]))
        out += [Spacer(1, 0.3 * cm), tbl, Spacer(1, 0.5 * cm)]
        return out

    def _appendix(self, analysis: ReportAnalysis, styles) -> list:
        return [
            Paragraph("Appendix — Report Metadata", styles["Heading2"]),
            HRFlowable(width="100%"),
            Spacer(1, 0.3 * cm),
            Paragraph(f"Export Document ID: {analysis.export_document_id}", styles["Normal"]),
            Paragraph(f"Organization ID: {analysis.org_id}", styles["Normal"]),
            Paragraph(f"Framework: {analysis.framework}", styles["Normal"]),
            Paragraph(f"Generated at: {analysis.generated_at.isoformat()}", styles["Normal"]),
        ]
