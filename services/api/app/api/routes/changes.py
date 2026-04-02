"""
Change record routes — full lifecycle + simulation + webhooks
"""
from uuid import UUID
from fastapi import APIRouter, HTTPException, Depends, Request
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import schemas
from app.api import dependencies
from app.api.dependencies import get_db, get_current_user
from app.api.rate_limit import limiter, LIMIT_READ, LIMIT_WRITE
from app.core.config import settings
from app.services.change_service import VALID_TRANSITIONS, can_transition, generate_change_number

router = APIRouter()


# =============================================================================
# CHANGE RECORDS
# =============================================================================

from app.services.change_service import VALID_TRANSITIONS, can_transition, generate_change_number


TRANSITION_ROLES = {
    "approve": "admin",
    "verify": "admin",
    "rollback": "admin",
}


@router.post("/changes", response_model=schemas.ChangeRecordResponse, status_code=201)
@limiter.limit(LIMIT_WRITE)
async def create_change_record(request: Request, 
    change: schemas.ChangeRecordCreate,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new change record (status=draft)"""
    from uuid import UUID, uuid4
    from app.models.models import ChangeRecord

    org_id = UUID(current_user.organization_id)
    change_number = await generate_change_number(db)

    change_record = ChangeRecord(
        id=uuid4(),
        organization_id=org_id,
        change_number=change_number,
        status="draft",
        change_type=change.change_type,
        title=change.title,
        description=change.description,
        risk_level=change.risk_level,
        affected_devices=change.affected_devices,
        affected_compliance_scopes=change.affected_compliance_scopes,
        scheduled_window_start=change.scheduled_window_start,
        scheduled_window_end=change.scheduled_window_end,
        compliance_justification=change.compliance_justification,
        requested_by=UUID(current_user.id),
    )

    db.add(change_record)
    await db.commit()
    await db.refresh(change_record)

    await dependencies.audit_log(
        action="change_record.create",
        resource_type="change_record",
        resource_id=str(change_record.id),
        resource_name=change_record.change_number,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return schemas.ChangeRecordResponse(
        id=str(change_record.id),
        organization_id=str(change_record.organization_id),
        change_number=change_record.change_number,
        status=change_record.status,
        change_type=change_record.change_type,
        title=change_record.title,
        description=change_record.description,
        risk_level=change_record.risk_level,
        compliance_justification=change_record.compliance_justification,
        affected_devices=change_record.affected_devices or [],
        affected_compliance_scopes=change_record.affected_compliance_scopes or [],
        requested_by=(
            str(change_record.requested_by) if change_record.requested_by else None
        ),
        requested_at=change_record.requested_at,
        simulation_performed=change_record.simulation_performed,
        simulation_results=change_record.simulation_results,
        simulation_passed=change_record.simulation_passed,
        rollback_performed=change_record.rollback_performed,
        created_at=change_record.created_at,
        updated_at=change_record.updated_at,
    )


@router.get("/changes", response_model=schemas.ChangeRecordListResponse)
@limiter.limit(LIMIT_READ)
async def list_change_records(request: Request, 
    skip: int = 0,
    limit: int = 100,
    status: str | None = None,
    risk_level: str | None = None,
    device_id: str | None = None,
    compliance_scope: str | None = None,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List change records with optional filters"""
    from uuid import UUID
    from sqlalchemy import select, func
    from app.models.models import ChangeRecord

    org_id = UUID(current_user.organization_id)

    query = select(ChangeRecord).where(ChangeRecord.organization_id == org_id)

    if status:
        query = query.where(ChangeRecord.status == status)
    if risk_level:
        query = query.where(ChangeRecord.risk_level == risk_level)
    if device_id:
        query = query.where(ChangeRecord.affected_devices.contains([device_id]))
    if compliance_scope:
        query = query.where(
            ChangeRecord.affected_compliance_scopes.contains([compliance_scope])
        )

    count_query = (
        select(func.count())
        .select_from(ChangeRecord)
        .where(ChangeRecord.organization_id == org_id)
    )
    if status:
        count_query = count_query.where(ChangeRecord.status == status)
    if risk_level:
        count_query = count_query.where(ChangeRecord.risk_level == risk_level)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.offset(skip).limit(limit).order_by(ChangeRecord.requested_at.desc())
    result = await db.execute(query)
    changes = result.scalars().all()

    return schemas.ChangeRecordListResponse(
        items=[
            schemas.ChangeRecordResponse(
                id=str(c.id),
                organization_id=str(c.organization_id),
                change_number=c.change_number,
                status=c.status,
                change_type=c.change_type,
                title=c.title,
                description=c.description,
                risk_level=c.risk_level,
                compliance_justification=c.compliance_justification,
                affected_devices=c.affected_devices or [],
                affected_compliance_scopes=c.affected_compliance_scopes or [],
                requested_by=str(c.requested_by) if c.requested_by else None,
                requested_at=c.requested_at,
                approved_by=str(c.approved_by) if c.approved_by else None,
                approved_at=c.approved_at,
                approval_notes=c.approval_notes,
                proposed_change_hash=c.proposed_change_hash,
                pre_change_hash=c.pre_change_hash,
                post_change_hash=c.post_change_hash,
                simulation_performed=c.simulation_performed,
                simulation_results=c.simulation_results,
                simulation_passed=c.simulation_passed,
                implemented_by=str(c.implemented_by) if c.implemented_by else None,
                implemented_at=c.implemented_at,
                implementation_evidence=c.implementation_evidence,
                verification_results=c.verification_results,
                verification_passed=c.verification_passed,
                rollback_performed=c.rollback_performed,
                rollback_at=c.rollback_at,
                rollback_reason=c.rollback_reason,
                external_ticket_id=c.external_ticket_id,
                external_ticket_url=c.external_ticket_url,
                ticket_system=c.ticket_system,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in changes
        ],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/changes/{change_id}", response_model=schemas.ChangeRecordResponse)
@limiter.limit(LIMIT_READ)
async def get_change_record(request: Request, 
    change_id: str,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific change record"""
    from uuid import UUID
    from sqlalchemy import select
    from fastapi import HTTPException
    from app.models.models import ChangeRecord

    try:
        change_uuid = UUID(change_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid change ID format")

    org_id = UUID(current_user.organization_id)
    result = await db.execute(
        select(ChangeRecord).where(
            ChangeRecord.id == change_uuid,
            ChangeRecord.organization_id == org_id,
        )
    )
    change = result.scalar_one_or_none()

    if not change:
        raise HTTPException(status_code=404, detail="Change record not found")

    return schemas.ChangeRecordResponse(
        id=str(change.id),
        organization_id=str(change.organization_id),
        change_number=change.change_number,
        status=change.status,
        change_type=change.change_type,
        title=change.title,
        description=change.description,
        risk_level=change.risk_level,
        compliance_justification=change.compliance_justification,
        affected_devices=change.affected_devices or [],
        affected_compliance_scopes=change.affected_compliance_scopes or [],
        requested_by=str(change.requested_by) if change.requested_by else None,
        requested_at=change.requested_at,
        approved_by=str(change.approved_by) if change.approved_by else None,
        approved_at=change.approved_at,
        approval_notes=change.approval_notes,
        proposed_change_hash=change.proposed_change_hash,
        pre_change_hash=change.pre_change_hash,
        post_change_hash=change.post_change_hash,
        simulation_performed=change.simulation_performed,
        simulation_results=change.simulation_results,
        simulation_passed=change.simulation_passed,
        implemented_by=str(change.implemented_by) if change.implemented_by else None,
        implemented_at=change.implemented_at,
        implementation_evidence=change.implementation_evidence,
        verification_results=change.verification_results,
        verification_passed=change.verification_passed,
        rollback_performed=change.rollback_performed,
        rollback_at=change.rollback_at,
        rollback_reason=change.rollback_reason,
        external_ticket_id=change.external_ticket_id,
        external_ticket_url=change.external_ticket_url,
        ticket_system=change.ticket_system,
        created_at=change.created_at,
        updated_at=change.updated_at,
    )


@router.patch("/changes/{change_id}", response_model=schemas.ChangeRecordResponse)
@limiter.limit(LIMIT_WRITE)
async def update_change_record(request: Request, 
    change_id: str,
    change_update: schemas.ChangeRecordUpdate,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a change record (draft/proposed status only)"""
    from uuid import UUID
    from sqlalchemy import select
    from fastapi import HTTPException
    from app.models.models import ChangeRecord

    try:
        change_uuid = UUID(change_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid change ID format")

    org_id = UUID(current_user.organization_id)
    result = await db.execute(
        select(ChangeRecord).where(
            ChangeRecord.id == change_uuid,
            ChangeRecord.organization_id == org_id,
        )
    )
    change = result.scalar_one_or_none()

    if not change:
        raise HTTPException(status_code=404, detail="Change record not found")

    if change.status not in ["draft", "proposed"]:
        raise HTTPException(
            status_code=400, detail=f"Cannot update change in '{change.status}' status"
        )

    update_data = change_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(change, field, value)

    await db.commit()
    await db.refresh(change)

    await dependencies.audit_log(
        action="change_record.update",
        resource_type="change_record",
        resource_id=str(change.id),
        resource_name=change.change_number,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return schemas.ChangeRecordResponse(
        id=str(change.id),
        organization_id=str(change.organization_id),
        change_number=change.change_number,
        status=change.status,
        change_type=change.change_type,
        title=change.title,
        description=change.description,
        risk_level=change.risk_level,
        compliance_justification=change.compliance_justification,
        affected_devices=change.affected_devices or [],
        affected_compliance_scopes=change.affected_compliance_scopes or [],
        requested_by=str(change.requested_by) if change.requested_by else None,
        requested_at=change.requested_at,
        approved_by=str(change.approved_by) if change.approved_by else None,
        approved_at=change.approved_at,
        approval_notes=change.approval_notes,
        proposed_change_hash=change.proposed_change_hash,
        pre_change_hash=change.pre_change_hash,
        post_change_hash=change.post_change_hash,
        simulation_performed=change.simulation_performed,
        simulation_results=change.simulation_results,
        simulation_passed=change.simulation_passed,
        implemented_by=str(change.implemented_by) if change.implemented_by else None,
        implemented_at=change.implemented_at,
        implementation_evidence=change.implementation_evidence,
        verification_results=change.verification_results,
        verification_passed=change.verification_passed,
        rollback_performed=change.rollback_performed,
        rollback_at=change.rollback_at,
        rollback_reason=change.rollback_reason,
        external_ticket_id=change.external_ticket_id,
        external_ticket_url=change.external_ticket_url,
        ticket_system=change.ticket_system,
        created_at=change.created_at,
        updated_at=change.updated_at,
    )


@router.delete("/changes/{change_id}", status_code=204)
@limiter.limit(LIMIT_WRITE)
async def delete_change_record(request: Request, 
    change_id: str,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a change record (draft status only)"""
    from uuid import UUID
    from sqlalchemy import select
    from fastapi import HTTPException
    from app.models.models import ChangeRecord

    try:
        change_uuid = UUID(change_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid change ID format")

    org_id = UUID(current_user.organization_id)
    result = await db.execute(
        select(ChangeRecord).where(
            ChangeRecord.id == change_uuid,
            ChangeRecord.organization_id == org_id,
        )
    )
    change = result.scalar_one_or_none()

    if not change:
        raise HTTPException(status_code=404, detail="Change record not found")

    if change.status != "draft":
        raise HTTPException(
            status_code=400, detail="Can only delete change records in draft status"
        )

    await db.delete(change)
    await db.commit()

    await dependencies.audit_log(
        action="change_record.delete",
        resource_type="change_record",
        resource_id=change_id,
        resource_name=change.change_number,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return None


@router.post(
    "/changes/{change_id}/propose", response_model=schemas.ChangeRecordResponse
)
@limiter.limit(LIMIT_WRITE)
async def propose_change(
    change_id: str,
    request: schemas.ChangeProposeRequest,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit change for approval; capture proposed change hash"""
    from uuid import UUID
    from app.models.models import ChangeRecord

    try:
        change_uuid = UUID(change_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid change ID format")

    org_id = UUID(current_user.organization_id)
    result = await db.execute(
        select(ChangeRecord).where(
            ChangeRecord.id == change_uuid,
            ChangeRecord.organization_id == org_id,
        )
    )
    change = result.scalar_one_or_none()

    if not change:
        raise HTTPException(status_code=404, detail="Change record not found")

    if not can_transition(change.status, "proposed"):
        raise HTTPException(
            status_code=400, detail=f"Cannot propose change in '{change.status}' status"
        )

    if not change.affected_devices:
        raise HTTPException(
            status_code=400, detail="At least one affected device must be specified"
        )

    change.status = "proposed"
    change.proposed_change_hash = request.proposed_change_hash

    await db.commit()
    await db.refresh(change)

    await dependencies.audit_log(
        action="change_record.propose",
        resource_type="change_record",
        resource_id=str(change.id),
        resource_name=change.change_number,
        outcome="success",
        details={"proposed_change_hash": request.proposed_change_hash},
        current_user=current_user,
        db=db,
    )

    return schemas.ChangeRecordResponse(
        id=str(change.id),
        organization_id=str(change.organization_id),
        change_number=change.change_number,
        status=change.status,
        change_type=change.change_type,
        title=change.title,
        description=change.description,
        risk_level=change.risk_level,
        affected_devices=change.affected_devices or [],
        affected_compliance_scopes=change.affected_compliance_scopes or [],
        requested_by=str(change.requested_by) if change.requested_by else None,
        requested_at=change.requested_at,
        proposed_change_hash=change.proposed_change_hash,
        pre_change_hash=change.pre_change_hash,
        simulation_performed=change.simulation_performed,
        simulation_passed=change.simulation_passed,
        created_at=change.created_at,
        updated_at=change.updated_at,
    )


@router.post(
    "/changes/{change_id}/approve", response_model=schemas.ChangeRecordResponse
)
@limiter.limit(LIMIT_WRITE)
async def approve_change(
    change_id: str,
    request: schemas.ChangeApproveRequest,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Approve a proposed change (requires admin role)"""
    from uuid import UUID
    from sqlalchemy import select
    from fastapi import HTTPException
    from datetime import datetime
    from app.models.models import ChangeRecord

    if current_user.role != "admin":
        raise HTTPException(
            status_code=403, detail="Only administrators can approve changes"
        )

    try:
        change_uuid = UUID(change_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid change ID format")

    org_id = UUID(current_user.organization_id)
    result = await db.execute(
        select(ChangeRecord).where(
            ChangeRecord.id == change_uuid,
            ChangeRecord.organization_id == org_id,
        )
    )
    change = result.scalar_one_or_none()

    if not change:
        raise HTTPException(status_code=404, detail="Change record not found")

    if not can_transition(change.status, "approved"):
        raise HTTPException(
            status_code=400, detail=f"Cannot approve change in '{change.status}' status"
        )

    if change.simulation_performed and not change.simulation_passed:
        raise HTTPException(
            status_code=400, detail="Simulation must pass before approval"
        )

    change.status = "approved"
    change.approved_by = UUID(current_user.id)
    change.approved_at = datetime.utcnow()
    change.approval_notes = request.approval_notes

    await db.commit()
    await db.refresh(change)

    await dependencies.audit_log(
        action="change_record.approve",
        resource_type="change_record",
        resource_id=str(change.id),
        resource_name=change.change_number,
        outcome="success",
        details={"approval_notes": request.approval_notes},
        current_user=current_user,
        db=db,
    )

    return schemas.ChangeRecordResponse(
        id=str(change.id),
        organization_id=str(change.organization_id),
        change_number=change.change_number,
        status=change.status,
        title=change.title,
        approved_by=str(change.approved_by) if change.approved_by else None,
        approved_at=change.approved_at,
        approval_notes=change.approval_notes,
        created_at=change.created_at,
        updated_at=change.updated_at,
    )


@router.post(
    "/changes/{change_id}/implement", response_model=schemas.ChangeRecordResponse
)
@limiter.limit(LIMIT_WRITE)
async def implement_change(
    change_id: str,
    request: schemas.ChangeImplementRequest,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Implement an approved change"""
    from uuid import UUID
    from sqlalchemy import select
    from fastapi import HTTPException
    from datetime import datetime
    from app.models.models import ChangeRecord

    try:
        change_uuid = UUID(change_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid change ID format")

    org_id = UUID(current_user.organization_id)
    result = await db.execute(
        select(ChangeRecord).where(
            ChangeRecord.id == change_uuid,
            ChangeRecord.organization_id == org_id,
        )
    )
    change = result.scalar_one_or_none()

    if not change:
        raise HTTPException(status_code=404, detail="Change record not found")

    if not can_transition(change.status, "in_progress"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot implement change in '{change.status}' status",
        )

    change.status = "in_progress"
    change.implemented_by = UUID(current_user.id)
    change.implemented_at = datetime.utcnow()
    change.implementation_evidence = request.implementation_evidence
    change.post_change_hash = request.post_change_hash

    await db.commit()
    await db.refresh(change)

    await dependencies.audit_log(
        action="change_record.implement",
        resource_type="change_record",
        resource_id=str(change.id),
        resource_name=change.change_number,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return schemas.ChangeRecordResponse(
        id=str(change.id),
        organization_id=str(change.organization_id),
        change_number=change.change_number,
        status=change.status,
        implemented_by=str(change.implemented_by) if change.implemented_by else None,
        implemented_at=change.implemented_at,
        implementation_evidence=change.implementation_evidence,
        post_change_hash=change.post_change_hash,
        created_at=change.created_at,
        updated_at=change.updated_at,
    )


@router.post("/changes/{change_id}/verify", response_model=schemas.ChangeRecordResponse)
@limiter.limit(LIMIT_WRITE)
async def verify_change(
    change_id: str,
    request: schemas.ChangeVerifyRequest,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify a implemented change (requires admin role)"""
    from uuid import UUID
    from app.models.models import ChangeRecord

    if current_user.role != "admin":
        raise HTTPException(
            status_code=403, detail="Only administrators can verify changes"
        )

    try:
        change_uuid = UUID(change_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid change ID format")

    org_id = UUID(current_user.organization_id)
    result = await db.execute(
        select(ChangeRecord).where(
            ChangeRecord.id == change_uuid,
            ChangeRecord.organization_id == org_id,
        )
    )
    change = result.scalar_one_or_none()

    if not change:
        raise HTTPException(status_code=404, detail="Change record not found")

    if change.status != "in_progress":
        raise HTTPException(
            status_code=400, detail="Can only verify changes in in_progress status"
        )

    change.status = "completed"
    change.verification_results = request.verification_results
    change.verification_passed = (
        request.verification_results.get("passed", False)
        if request.verification_results
        else False
    )

    await db.commit()
    await db.refresh(change)

    await dependencies.audit_log(
        action="change_record.verify",
        resource_type="change_record",
        resource_id=str(change.id),
        resource_name=change.change_number,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return schemas.ChangeRecordResponse(
        id=str(change.id),
        organization_id=str(change.organization_id),
        change_number=change.change_number,
        status=change.status,
        verification_results=change.verification_results,
        verification_passed=change.verification_passed,
        created_at=change.created_at,
        updated_at=change.updated_at,
    )


@router.post(
    "/changes/{change_id}/rollback", response_model=schemas.ChangeRecordResponse
)
@limiter.limit(LIMIT_WRITE)
async def rollback_change(
    change_id: str,
    request: schemas.ChangeRollbackRequest,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Rollback a change (requires admin role)"""
    from uuid import UUID
    from sqlalchemy import select
    from fastapi import HTTPException
    from datetime import datetime
    from app.models.models import ChangeRecord

    if current_user.role != "admin":
        raise HTTPException(
            status_code=403, detail="Only administrators can rollback changes"
        )

    try:
        change_uuid = UUID(change_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid change ID format")

    org_id = UUID(current_user.organization_id)
    result = await db.execute(
        select(ChangeRecord).where(
            ChangeRecord.id == change_uuid,
            ChangeRecord.organization_id == org_id,
        )
    )
    change = result.scalar_one_or_none()

    if not change:
        raise HTTPException(status_code=404, detail="Change record not found")

    if not can_transition(change.status, "rolled_back"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot rollback change in '{change.status}' status",
        )

    change.status = "rolled_back"
    change.rollback_performed = True
    change.rollback_at = datetime.utcnow()
    change.rollback_reason = request.rollback_reason

    await db.commit()
    await db.refresh(change)

    await dependencies.audit_log(
        action="change_record.rollback",
        resource_type="change_record",
        resource_id=str(change.id),
        resource_name=change.change_number,
        outcome="success",
        details={"rollback_reason": request.rollback_reason},
        current_user=current_user,
        db=db,
    )

    return schemas.ChangeRecordResponse(
        id=str(change.id),
        organization_id=str(change.organization_id),
        change_number=change.change_number,
        status=change.status,
        rollback_performed=change.rollback_performed,
        rollback_at=change.rollback_at,
        rollback_reason=change.rollback_reason,
        created_at=change.created_at,
        updated_at=change.updated_at,
    )


@router.post(
    "/changes/{change_id}/sync-ticket", response_model=schemas.ChangeRecordResponse
)
@limiter.limit(LIMIT_WRITE)
async def sync_change_to_ticket(
    change_id: str,
    request: schemas.ChangeSyncTicketRequest,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sync change record to external ticketing system"""
    from uuid import UUID
    from sqlalchemy import select
    from fastapi import HTTPException
    from app.models.models import ChangeRecord, IntegrationConfig
    from app.services.ticket_sync import ticket_sync_service

    try:
        change_uuid = UUID(change_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid change ID format")

    org_id = UUID(current_user.organization_id)

    result = await db.execute(
        select(ChangeRecord).where(
            ChangeRecord.id == change_uuid,
            ChangeRecord.organization_id == org_id,
        )
    )
    change = result.scalar_one_or_none()

    if not change:
        raise HTTPException(status_code=404, detail="Change record not found")

    integ_result = await db.execute(
        select(IntegrationConfig).where(
            IntegrationConfig.organization_id == org_id,
            IntegrationConfig.integration_type == request.ticket_system,
            IntegrationConfig.is_enabled == True,
        )
    )
    integration = integ_result.scalar_one_or_none()

    if not integration:
        raise HTTPException(
            status_code=404,
            detail=f"No enabled {request.ticket_system} integration found",
        )

    try:
        if request.ticket_system == "servicenow":
            ticket_result = await ticket_sync_service.create_servicenow_ticket(
                change, integration
            )
        elif request.ticket_system == "jira":
            ticket_result = await ticket_sync_service.create_jira_ticket(
                change, integration
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported ticket system: {request.ticket_system}",
            )

        change.external_ticket_id = ticket_result.get("ticket_id") or ticket_result.get(
            "ticket_key"
        )
        change.external_ticket_url = ticket_result.get("ticket_url")
        change.ticket_system = request.ticket_system

        await db.commit()
        await db.refresh(change)

    except Exception as e:
        raise HTTPException(
            status_code=502, detail=f"Failed to create ticket: {str(e)}"
        )

    return schemas.ChangeRecordResponse(
        id=str(change.id),
        organization_id=str(change.organization_id),
        change_number=change.change_number,
        status=change.status,
        external_ticket_id=change.external_ticket_id,
        external_ticket_url=change.external_ticket_url,
        ticket_system=change.ticket_system,
        updated_at=change.updated_at,
    )


@router.post("/webhooks/change/{integration_id}")
async def change_webhook(
    integration_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    """Webhook receiver for external ticketing system approval"""
    from uuid import UUID
    from sqlalchemy import select
    from fastapi import HTTPException
    from app.models.models import IntegrationConfig, ChangeRecord

    try:
        integ_uuid = UUID(integration_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid integration ID")

    result = await db.execute(
        select(IntegrationConfig).where(IntegrationConfig.id == integ_uuid)
    )
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    if integration.integration_type == "servicenow":
        change_request_id = payload.get("sys_id") or payload.get(
            "change_request", {}
        ).get("sys_id")
        state = payload.get("state") or payload.get("change_request", {}).get("state")

        if state in ["3", "approved"]:
            cr_result = await db.execute(
                select(ChangeRecord).where(
                    ChangeRecord.external_ticket_id == change_request_id
                )
            )
            change = cr_result.scalar_one_or_none()

            if change and change.status == "proposed":
                from datetime import datetime

                change.status = "approved"
                change.approved_at = datetime.utcnow()
                change.approval_notes = "Auto-approved via ServiceNow webhook"
                await db.commit()

    elif integration.integration_type == "jira":
        issue_key = payload.get("issue", {}).get("key")
        transition = payload.get("transition", {}).get("name", "").lower()

        if "approve" in transition or "resolved" in transition:
            cr_result = await db.execute(
                select(ChangeRecord).where(ChangeRecord.external_ticket_id == issue_key)
            )
            change = cr_result.scalar_one_or_none()

            if change and change.status == "proposed":
                from datetime import datetime

                change.status = "approved"
                change.approved_at = datetime.utcnow()
                change.approval_notes = "Auto-approved via JIRA webhook"
                await db.commit()

    return {"status": "received"}


# =============================================================================
# CHANGE SIMULATION (ContainerLab)
# =============================================================================
@router.post(
    "/changes/{change_id}/simulate", response_model=schemas.ChangeSimulateResponse
)
@limiter.limit(LIMIT_WRITE)
async def trigger_simulation(
    change_id: str,
    request: schemas.ChangeSimulateRequest,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger ContainerLab simulation for a proposed change"""
    from uuid import UUID
    from sqlalchemy import select
    from app.models.models import ChangeRecord
    from datetime import datetime
    from uuid import uuid4

    try:
        change_uuid = UUID(change_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid change ID format")

    org_id = UUID(current_user.organization_id)
    result = await db.execute(
        select(ChangeRecord).where(
            ChangeRecord.id == change_uuid,
            ChangeRecord.organization_id == org_id,
        )
    )
    change = result.scalar_one_or_none()

    if not change:
        raise HTTPException(status_code=404, detail="Change record not found")

    if change.status != "proposed":
        raise HTTPException(
            status_code=400, detail="Can only simulate changes in proposed status"
        )

    simulation_id = str(uuid4())

    import redis.asyncio as redis

    redis_client = redis.from_url(settings.REDIS_URL)
    await redis_client.hset(
        f"simulation:{simulation_id}",
        mapping={
            "change_id": str(change.id),
            "organization_id": str(org_id),
            "proposed_config": request.proposed_config,
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
        },
    )
    await redis_client.expire(f"simulation:{simulation_id}", 3600)
    await redis_client.close()

    change.simulation_performed = True
    change.simulation_results = {
        "simulation_id": simulation_id,
        "status": "started",
        "started_at": datetime.utcnow().isoformat(),
    }

    await db.commit()

    await dependencies.audit_log(
        action="change_record.simulate",
        resource_type="change_record",
        resource_id=str(change.id),
        resource_name=change.change_number,
        outcome="success",
        details={"simulation_id": simulation_id},
        current_user=current_user,
        db=db,
    )

    return schemas.ChangeSimulateResponse(
        change_id=str(change.id),
        simulation_id=simulation_id,
        status="started",
    )


@router.get(
    "/changes/{change_id}/simulation-results",
    response_model=schemas.ChangeRecordResponse,
)
@limiter.limit(LIMIT_READ)
async def get_simulation_results(request: Request, 
    change_id: str,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get simulation results for a change"""
    from uuid import UUID
    from sqlalchemy import select
    from app.models.models import ChangeRecord

    try:
        change_uuid = UUID(change_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid change ID format")

    org_id = UUID(current_user.organization_id)
    result = await db.execute(
        select(ChangeRecord).where(
            ChangeRecord.id == change_uuid,
            ChangeRecord.organization_id == org_id,
        )
    )
    change = result.scalar_one_or_none()

    if not change:
        raise HTTPException(status_code=404, detail="Change record not found")

    return schemas.ChangeRecordResponse(
        id=str(change.id),
        organization_id=str(change.organization_id),
        device_id=str(change.device_id),
        change_number=change.change_number,
        title=change.title,
        description=change.description,
        proposed_config=change.proposed_config,
        current_config=change.current_config,
        status=change.status,
        risk_level=change.risk_level,
        simulation_performed=change.simulation_performed,
        simulation_results=change.simulation_results,
        simulation_passed=change.simulation_passed,
        external_ticket_id=change.external_ticket_id,
        external_ticket_url=change.external_ticket_url,
        ticket_system=change.ticket_system,
        created_at=change.created_at,
        updated_at=change.updated_at,
    )


