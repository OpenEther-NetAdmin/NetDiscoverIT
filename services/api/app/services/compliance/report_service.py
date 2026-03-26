"""
report_service — orchestrates compliance report generation.

Called via asyncio.create_task from the API route. Updates ExportDocument
status throughout. Never raises — all exceptions are caught and recorded.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import ExportDocument
from app.services.compliance.docx_renderer import DOCXRenderer
from app.services.compliance.evidence_collector import EvidenceCollector
from app.services.compliance.framework_analyzer import FrameworkAnalyzer
from app.services.compliance.pdf_renderer import PDFRenderer
from app.services.storage import storage_service

logger = logging.getLogger(__name__)

_MIME = {"pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
_EXT  = {"pdf": "pdf", "docx": "docx"}


async def generate_report(
    export_document_id: str,
    org_id: str,
    org_name: str,
    framework: str,
    report_format: str,
    period_start: datetime,
    period_end: datetime,
    db: AsyncSession,
    neo4j_client,
    scope_override: list[str] | None = None,
) -> None:
    result = await db.execute(
        select(ExportDocument).where(ExportDocument.id == UUID(export_document_id))
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        logger.error("ExportDocument %s not found — aborting generate_report", export_document_id)
        return

    doc.status = "generating"
    await db.commit()

    try:
        collector = EvidenceCollector()
        pkg = await collector.collect(
            db=db,
            neo4j_client=neo4j_client,
            org_id=org_id,
            framework=framework,
            period_start=period_start,
            period_end=period_end,
            scope_override=scope_override,
        )

        analyzer = FrameworkAnalyzer()
        analysis = analyzer.analyze(pkg, export_document_id=export_document_id)

        if report_format == "pdf":
            renderer = PDFRenderer()
            file_bytes = renderer.render(analysis, org_name=org_name)
        else:
            renderer = DOCXRenderer()
            file_bytes = renderer.render(analysis, org_name=org_name)

        filename = f"compliance-{framework}-{period_start.strftime('%Y%m%d')}.{_EXT[report_format]}"
        storage_path = storage_service.upload_file(
            org_id=org_id,
            filename=filename,
            data=file_bytes,
            content_type=_MIME[report_format],
        )

        doc.status = "completed"
        doc.storage_path = storage_path
        doc.file_size_bytes = len(file_bytes)
        doc.completed_at = datetime.now(timezone.utc)
        await db.commit()
        logger.info("Report %s completed — %d bytes at %s", export_document_id, len(file_bytes), storage_path)

    except Exception as exc:
        logger.exception("Report generation failed for %s: %s", export_document_id, exc)
        doc.status = "failed"
        doc.error_message = str(exc)
        await db.commit()
