"""
Compliance report routes — async PDF/DOCX generation per regulatory framework.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import schemas
from app.api.dependencies import get_current_user, get_db
from app.db.neo4j import get_neo4j_client
from app.models.models import ExportDocument, Organization
from app.services.compliance.report_service import generate_report
from app.services.storage import storage_service, StorageError

logger = logging.getLogger(__name__)
router = APIRouter()

_FORMAT_TO_MIME = {
    "pdf":  "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@router.post("", response_model=schemas.ComplianceReportResponse, status_code=202)
async def create_compliance_report(
    request: schemas.ComplianceReportCreate,
    current_user: schemas.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger async compliance report generation. Returns ExportDocument ID immediately."""
    org_uuid = UUID(current_user.organization_id)

    org_result = await db.execute(
        select(Organization).where(Organization.id == org_uuid)
    )
    org = org_result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    if request.format == "both":
        doc_ids = []
        for fmt in ("pdf", "docx"):
            doc = ExportDocument(
                organization_id=org_uuid,
                requested_by=UUID(current_user.id),
                document_type="compliance_report",
                format=fmt,
                status="pending",
                parameters={
                    "framework": request.framework,
                    "period_start": request.period_start.isoformat(),
                    "period_end": request.period_end.isoformat(),
                    "scope_override": request.scope_override,
                },
            )
            db.add(doc)
            await db.commit()
            await db.refresh(doc)
            doc_ids.append(str(doc.id))

            neo4j = await get_neo4j_client()
            asyncio.create_task(generate_report(
                export_document_id=str(doc.id),
                org_id=str(org_uuid),
                org_name=org.name or str(org_uuid),
                framework=request.framework,
                report_format=fmt,
                period_start=request.period_start,
                period_end=request.period_end,
                neo4j_client=neo4j,
                scope_override=request.scope_override,
            ))

        return schemas.ComplianceReportResponse(
            id=doc_ids[0],
            status="pending",
            framework=request.framework,
            format="pdf",
        )

    doc = ExportDocument(
        organization_id=org_uuid,
        requested_by=UUID(current_user.id),
        document_type="compliance_report",
        format=request.format,
        status="pending",
        parameters={
            "framework": request.framework,
            "period_start": request.period_start.isoformat(),
            "period_end": request.period_end.isoformat(),
            "scope_override": request.scope_override,
        },
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    neo4j = await get_neo4j_client()
    asyncio.create_task(generate_report(
        export_document_id=str(doc.id),
        org_id=str(org_uuid),
        org_name=org.name or str(org_uuid),
        framework=request.framework,
        report_format=request.format,
        period_start=request.period_start,
        period_end=request.period_end,
        neo4j_client=neo4j,
        scope_override=request.scope_override,
    ))

    return schemas.ComplianceReportResponse(
        id=str(doc.id),
        status="pending",
        framework=request.framework,
        format=request.format,
        created_at=doc.created_at,
    )


@router.get("/{report_id}", response_model=schemas.ComplianceReportResponse)
async def get_compliance_report(
    report_id: str,
    current_user: schemas.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Poll report status. Returns presigned download URL when completed."""
    try:
        report_uuid = UUID(report_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid report ID")

    result = await db.execute(
        select(ExportDocument).where(
            ExportDocument.id == report_uuid,
            ExportDocument.organization_id == UUID(current_user.organization_id),
            ExportDocument.document_type == "compliance_report",
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Report not found")

    download_url = None
    if doc.status == "completed" and doc.storage_path:
        try:
            download_url = storage_service.generate_presigned_url(doc.storage_path)
        except StorageError as exc:
            logger.warning("Could not generate presigned URL for %s: %s", report_id, exc)

    params = doc.parameters or {}
    return schemas.ComplianceReportResponse(
        id=str(doc.id),
        status=doc.status,
        framework=params.get("framework", ""),
        format=doc.format,
        download_url=download_url,
        error_message=doc.error_message,
        created_at=doc.created_at,
        completed_at=doc.completed_at,
    )


@router.get("", response_model=schemas.ComplianceReportListResponse)
async def list_compliance_reports(
    status: str | None = None,
    framework: str | None = None,
    skip: int = 0,
    limit: int = 20,
    current_user: schemas.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List compliance reports for the authenticated user's organization."""
    org_uuid = UUID(current_user.organization_id)
    query = select(ExportDocument).where(
        ExportDocument.organization_id == org_uuid,
        ExportDocument.document_type == "compliance_report",
    )
    if status:
        query = query.where(ExportDocument.status == status)
    if framework:
        query = query.where(ExportDocument.parameters["framework"].as_string() == framework)

    query = query.order_by(ExportDocument.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    docs = result.scalars().all()

    items = []
    for doc in docs:
        params = doc.parameters or {}
        download_url = None
        if doc.status == "completed" and doc.storage_path:
            try:
                download_url = storage_service.generate_presigned_url(doc.storage_path)
            except StorageError:
                pass
        items.append(schemas.ComplianceReportResponse(
            id=str(doc.id),
            status=doc.status,
            framework=params.get("framework", ""),
            format=doc.format,
            download_url=download_url,
            error_message=doc.error_message,
            created_at=doc.created_at,
            completed_at=doc.completed_at,
        ))

    return schemas.ComplianceReportListResponse(
        items=items,
        total=len(items),
        skip=skip,
        limit=limit,
    )
