# Design: Group 8b — Compliance Report Generation (PDF + DOCX)

**Date:** 2026-03-26
**Status:** Approved
**Depends on:** Group 8a (MinIO/StorageService — complete), Group 7 (NLI/RAG — complete)
**Out of scope:** 8c export formats (XLSX, Drawio, Visio) — deprioritized, not scheduled

---

## 1. Overview

Compliance report generation compiles audit-ready documentation per regulatory framework on demand. An engineer triggers generation via `POST /api/v1/compliance/reports`; the system queries existing evidence (device metadata, change records, audit logs, Neo4j topology), renders a PDF and/or DOCX, uploads to MinIO, and returns a presigned download URL when ready.

No new data collection is required — all evidence already exists in the database from normal platform operation.

---

## 2. Architecture

### Async Execution Model

Report generation runs as an `asyncio.create_task` background coroutine within the FastAPI process. This fits the existing codebase pattern (all DB ops are async, alerting tasks are plain async functions) and adds zero infrastructure. Celery can be layered in later if generation times exceed ~30 seconds in production.

### Request / Response Flow

```
POST /api/v1/compliance/reports
  │
  ├─ Validate request (framework, scope, period, format)
  ├─ Create ExportDocument (status=pending) in DB
  ├─ asyncio.create_task(generate_report(...))   ← fire-and-forget
  └─ Return { id, status="pending" }

generate_report() coroutine:
  ├─ Update ExportDocument → status=generating
  ├─ EvidenceCollector.collect(org_id, framework, scope, period)
  ├─ FrameworkAnalyzer.analyze(framework, evidence_package) → ReportAnalysis
  ├─ PDFRenderer.render(analysis) → bytes   (if format=pdf or both)
  ├─ DOCXRenderer.render(analysis) → bytes  (if format=docx or both)
  ├─ storage_service.upload_file(org_id, filename, bytes, mime)
  ├─ Update ExportDocument → status=completed, storage_path, file_size_bytes, completed_at
  └─ On exception → Update ExportDocument → status=failed, error_message

GET /api/v1/compliance/reports/{id}
  └─ completed  → presigned URL (1hr expiry)
     generating → status only
     failed     → error_message

GET /api/v1/compliance/reports
  └─ List org's ExportDocuments (pagination, filter by status/framework)
```

### Service Layout

```
services/api/app/services/compliance/
    __init__.py
    evidence_collector.py    — DB + Neo4j queries → EvidencePackage
    framework_analyzer.py    — EvidencePackage → ReportAnalysis (per framework)
    pdf_renderer.py          — ReportAnalysis → PDF bytes (reportlab)
    docx_renderer.py         — ReportAnalysis → DOCX bytes (python-docx)
    report_service.py        — orchestrator coroutine (generate_report)

services/api/app/api/routes/compliance_reports.py   — 3 endpoints
```

---

## 3. Data Model

### EvidencePackage (input to FrameworkAnalyzer)

```python
@dataclass
class DeviceEvidence:
    device_id: str
    hostname: str
    compliance_scope: list[str]   # e.g. ["PCI-CDE", "PCI-BOUNDARY"]
    security_posture: dict        # from Device.metadata:
                                  #   ssh_enabled, telnet_enabled, http_enabled,
                                  #   https_enabled, snmp_enabled, acl_count

@dataclass
class ChangeEvidence:
    change_number: str            # CHG-2026-NNNN
    title: str
    status: str
    requested_by: str
    approved_by: str | None
    approved_at: datetime | None
    pre_change_hash: str | None
    post_change_hash: str | None
    simulation_passed: bool | None
    affected_compliance_scopes: list[str]

@dataclass
class AuditEvidence:
    log_id: str
    action: str                   # "resource_type.verb"
    outcome: str                  # success / failure
    user_id: str | None
    performed_at: datetime

@dataclass
class PathEvidence:
    source_device_id: str
    target_device_id: str
    path: list[str]               # device IDs along the path
    hop_count: int

@dataclass
class EvidencePackage:
    framework: str
    org_id: str
    period_start: datetime
    period_end: datetime
    devices: list[DeviceEvidence]
    changes: list[ChangeEvidence]
    audit_events: list[AuditEvidence]
    topology_paths: list[PathEvidence]   # PCI/FedRAMP/NIST only
```

### ControlFinding (output of FrameworkAnalyzer)

```python
@dataclass
class ControlFinding:
    control_id: str               # "PCI-DSS Req 1.3.2"
    description: str
    status: Literal["pass", "fail", "informational"]
    evidence_refs: list[str]      # device IDs, CHG-YYYY-NNNN, audit log IDs
    notes: str                    # remediation hint if fail; observation if info

@dataclass
class ReportAnalysis:
    framework: str
    org_id: str
    period_start: datetime
    period_end: datetime
    generated_at: datetime
    findings: list[ControlFinding]
    devices: list[DeviceEvidence]     # passed through for scope section
    changes: list[ChangeEvidence]     # passed through for change evidence section
    audit_events: list[AuditEvidence] # passed through for audit trail section
    topology_paths: list[PathEvidence]
    export_document_id: str
```

---

## 4. Framework → Evidence Mapping

| Framework | Key Controls | Primary Evidence |
|-----------|-------------|-----------------|
| PCI-DSS | Req 1 (segmentation), Req 2 (secure config), Req 6/12 (change mgmt) | topology_paths + security_posture + changes |
| HIPAA | §164.312(e) transmission security, access controls, audit trail | devices (PHI scope) + audit_events + changes |
| SOX ITGC | CC6/CC7 change management, access controls | changes (full lifecycle) + audit_events |
| ISO 27001 | A.12.1.2 change mgmt, A.9 access control | changes + security_posture + audit_events |
| FedRAMP | AC-17 remote access, CM-3 change control, AU-2 audit | all evidence sources |
| SOC 2 | CC6 logical access, CC7 system ops, CC8 change mgmt | changes + audit_events + security_posture |
| NIST CSF | PR.AC, PR.IP, DE.CM, RS.MI | security_posture + changes + topology_paths |

**Scope tag → framework mapping** (which `compliance_scope` tags are in-scope per framework):

| Framework | Scope Tags |
|-----------|-----------|
| pci_dss | PCI-CDE, PCI-BOUNDARY |
| hipaa | HIPAA-PHI |
| sox_itgc | SOX-FINANCIAL |
| iso_27001 | ISO27001 |
| fedramp | FEDRAMP-BOUNDARY |
| soc2 | SOC2 |
| nist_csf | NIST-CSF |

---

## 5. Report Document Structure

Same structure rendered by both PDFRenderer and DOCXRenderer:

```
1. Cover Page
   Organization name | Report type | Assessment period | Generated date | Classification

2. Executive Summary
   In-scope device count | Pass/fail/info counts per control group | Overall posture

3. Scope
   Table: hostname | inferred_role | compliance_scope tags | site

4. Control Findings  (one subsection per control group)
   Control ID + description
   Status: PASS / FAIL / INFO
   Evidence table: source | reference ID | date | detail
   Remediation notes (if FAIL)

5. Change Management Evidence  (SOX/PCI/ISO/SOC2 heavy)
   Table: CHG-# | title | requested_at | approved_by | approved_at | sim_passed | status
   Only changes touching in-scope compliance scopes within the assessment period

6. Network Segmentation  (PCI-DSS / FedRAMP / NIST CSF only)
   Neo4j path analysis summary
   Boundary device list with ACL count

7. Audit Trail Summary
   Admin action counts by resource type
   High-risk actions table: credential access, key rotations, org changes

8. Appendix — Evidence Hashes
   config_hash per in-scope device (timestamped)
   Report metadata: generated_at | generated_by | org_id | export_document_id
```

---

## 6. API Endpoints

All under `/api/v1/compliance/reports`, require JWT auth (`get_current_user`).

### POST /api/v1/compliance/reports
Trigger async report generation.

**Request:**
```json
{
  "framework": "pci_dss",
  "format": "pdf",           // "pdf" | "docx" | "both" (both = two ExportDocument records, one per format)
  "period_start": "2026-01-01T00:00:00Z",
  "period_end":   "2026-03-31T23:59:59Z",
  "scope_override": ["PCI-CDE"]   // optional; defaults to all tags for framework
}
```

**Response 202:**
```json
{ "id": "<uuid>", "status": "pending" }
```

### GET /api/v1/compliance/reports/{id}
Poll generation status; return download URL when ready.

**Response:**
```json
{
  "id": "<uuid>",
  "status": "completed",
  "framework": "pci_dss",
  "format": "pdf",
  "download_url": "<presigned MinIO URL>",   // only when status=completed
  "error_message": null,                      // populated when status=failed
  "created_at": "...",
  "completed_at": "..."
}
```

### GET /api/v1/compliance/reports
List reports for the authenticated user's org.

**Query params:** `status`, `framework`, `limit` (default 20), `offset`

---

## 7. Error Handling

- `generate_report` wraps its entire body in `try/except Exception` — any unhandled error updates `ExportDocument.status = "failed"` with the error message. The API process is never crashed.
- If `storage_service.upload_file` raises `StorageError`, the ExportDocument is marked failed with the storage error detail.
- If Neo4j is unavailable, `topology_paths` is set to `[]` and generation continues (segmentation section notes "Neo4j unavailable").
- Validation errors (invalid framework, period_end before period_start) are returned synchronously as 422 before the background task is created.

---

## 8. New Dependencies

```
reportlab==4.2.5
python-docx==1.1.2
```

Add to `services/api/requirements.txt`. Both are pure Python; no system packages needed in the Docker image.

---

## 9. Testing Strategy

### Unit tests (`tests/api/test_compliance_reports.py`)
- `EvidenceCollector` — mock DB session + Neo4j client; verify correct queries per framework
- `FrameworkAnalyzer` — fixed EvidencePackage input; assert ControlFindings output (pass/fail logic)
- `PDFRenderer` — assert output is non-empty bytes and starts with `%PDF`
- `DOCXRenderer` — assert output is valid DOCX (open with python-docx, check sections present)
- `report_service.generate_report` — mock collector + analyzer + renderers + storage; verify ExportDocument status transitions

### Integration tests (`tests/api/test_compliance_reports_integration.py`)
- Full pipeline against real DB + real MinIO: POST → poll until completed → GET presigned URL responds 200
- Failed generation path: mock analyzer to raise → verify ExportDocument.status = "failed"

---

## 10. Alembic Migration

No schema changes needed — `ExportDocument` model and all evidence tables already exist.
The `parameters` JSONB column on `ExportDocument` stores the report request parameters.

---

## 11. Constraints & Decisions

| Decision | Rationale |
|----------|-----------|
| asyncio.create_task (not Celery) | Fits existing async codebase; no new infrastructure; report gen is IO-bound |
| reportlab + python-docx | Proven libraries; pure Python; no system deps in Docker image |
| Renderers accept ReportAnalysis (not raw evidence) | Decouples formatting from data logic; renderers have no DB access |
| topology_paths only for PCI/FedRAMP/NIST | Neo4j query is expensive; other frameworks don't need path analysis |
| scope_override optional | Defaults to standard tags per framework; power users can narrow scope |
| ExportDocument.expires_at = None for compliance reports | Compliance archives must be permanently retained |
