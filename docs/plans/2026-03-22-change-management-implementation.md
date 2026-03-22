# Change Management API Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement Group 2 — Change Management API with full CRUD, state transitions, external ticket sync, and ContainerLab simulation integration.

**Architecture:** 
- RESTful API endpoints in services/api/app/api/routes.py
- ChangeRecord model already exists in services/api/app/models/models.py
- Pydantic schemas to be added in services/api/app/api/schemas.py
- External integrations: ServiceNow Table API, JIRA REST API, ContainerLab (agent-side)

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic, PostgreSQL, Redis (for async tasks)

---

## Prerequisites

Before starting, verify:
- [ ] Group 1b (IntegrationConfig CRUD) is complete - required for ticket sync
- [ ] ChangeRecord model exists: `services/api/app/models/models.py:967-1107`
- [ ] API service running: `make up`

---

## Task 1: ChangeRecord Schemas (2a-prep)

### Overview
Add Pydantic schemas for ChangeRecord API requests/responses.

### Files
- Modify: `services/api/app/api/schemas.py`

### Step 1: Add ChangeRecord schemas

**Step 1.1: Read existing schemas file**

Run: `wc -l services/api/app/api/schemas.py`

**Step 1.2: Add schemas**

Modify: `services/api/app/api/schemas.py`

Add at end of file:
```python
class ChangeRecordCreate(BaseModel):
    """Change record creation request"""
    title: str
    description: str | None = None
    change_type: str  # config_change, firmware_upgrade, acl_update, routing_change
    risk_level: str = "medium"  # low, medium, high, critical
    affected_devices: list[str] = []
    affected_compliance_scopes: list[str] = []
    scheduled_window_start: datetime | None = None
    scheduled_window_end: datetime | None = None
    compliance_justification: str | None = None


class ChangeRecordUpdate(BaseModel):
    """Change record update request"""
    title: str | None = None
    description: str | None = None
    change_type: str | None = None
    risk_level: str | None = None
    affected_devices: list[str] | None = None
    affected_compliance_scopes: list[str] | None = None
    scheduled_window_start: datetime | None = None
    scheduled_window_end: datetime | None = None
    compliance_justification: str | None = None


class ChangeRecordResponse(BaseModel):
    """Change record response"""
    id: str
    organization_id: str
    change_number: str
    status: str
    change_type: str | None = None
    title: str
    description: str | None = None
    risk_level: str
    compliance_justification: str | None = None
    affected_devices: list[str]
    affected_compliance_scopes: list[str]
    requested_by: str | None = None
    requested_at: datetime | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    approval_notes: str | None = None
    proposed_change_hash: str | None = None
    pre_change_hash: str | None = None
    post_change_hash: str | None = None
    simulation_performed: bool = False
    simulation_results: dict | None = None
    simulation_passed: bool | None = None
    implemented_by: str | None = None
    implemented_at: datetime | None = None
    implementation_evidence: dict | None = None
    verification_results: dict | None = None
    verification_passed: bool | None = None
    rollback_performed: bool = False
    rollback_at: datetime | None = None
    rollback_reason: str | None = None
    external_ticket_id: str | None = None
    external_ticket_url: str | None = None
    ticket_system: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChangeRecordListResponse(BaseModel):
    """Paginated change record list"""
    items: list[ChangeRecordResponse]
    total: int
    skip: int
    limit: int


class ChangeProposeRequest(BaseModel):
    """Request to propose a change for approval"""
    proposed_change_hash: str  # SHA-256 of proposed config


class ChangeApproveRequest(BaseModel):
    """Request to approve a change"""
    approval_notes: str | None = None


class ChangeImplementRequest(BaseModel):
    """Request to implement an approved change"""
    implementation_evidence: dict | None = None  # CLI output, API responses
    post_change_hash: str  # SHA-256 of config after change


class ChangeVerifyRequest(BaseModel):
    """Request to verify a change"""
    verification_results: dict | None = None  # Automated check results


class ChangeRollbackRequest(BaseModel):
    """Request to rollback a change"""
    rollback_reason: str


class ChangeSimulateRequest(BaseModel):
    """Request to trigger ContainerLab simulation"""
    proposed_config: str  # Config to simulate


class ChangeSimulateResponse(BaseModel):
    """Response from simulation trigger"""
    change_id: str
    simulation_id: str
    status: str  # started, failed


class ChangeSyncTicketRequest(BaseModel):
    """Request to sync change to external ticketing"""
    ticket_system: str  # servicenow, jira
```

---

## Task 2: ChangeRecord CRUD Endpoints (2a)

### Overview
Implement full CRUD for ChangeRecord with change number generation.

### Files
- Modify: `services/api/app/api/routes.py`
- Test: `services/api/tests/api/test_changes.py`

### Step 1: Add change number generator

**Step 1.1: Add helper function**

Modify: `services/api/app/api/routes.py`

Add at end of file:
```python
async def generate_change_number(db: AsyncSession) -> str:
    """Generate unique change number: CHG-YYYY-NNNN"""
    from datetime import datetime
    from sqlalchemy import func, select
    
    year = datetime.utcnow().year
    prefix = f"CHG-{year}-"
    
    # Get count for current year
    result = await db.execute(
        select(func.count())
        .select_from(ChangeRecord)
        .where(ChangeRecord.change_number.like(f"{prefix}%"))
    )
    count = result.scalar() or 0
    
    return f"{prefix}{count + 1:04d}"
```

### Step 2: Add CRUD routes

**Step 2.1: Add imports**

At top of routes.py, ensure ChangeRecord is imported:
```python
from app.models.models import ChangeRecord
```

**Step 2.2: Add CRUD routes**

Modify: `services/api/app/api/routes.py`

Add after integration routes (~line 600):
```python
# =============================================================================
# CHANGE RECORDS
# =============================================================================

@router.post("/changes", response_model=schemas.ChangeRecordResponse, status_code=201)
async def create_change_record(
    change: schemas.ChangeRecordCreate,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new change record (status=draft)"""
    from uuid import UUID, uuid4
    
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
        requested_by=str(change_record.requested_by) if change_record.requested_by else None,
        requested_at=change_record.requested_at,
        simulation_performed=change_record.simulation_performed,
        simulation_results=change_record.simulation_results,
        simulation_passed=change_record.simulation_passed,
        rollback_performed=change_record.rollback_performed,
        created_at=change_record.created_at,
        updated_at=change_record.updated_at,
    )


@router.get("/changes", response_model=schemas.ChangeRecordListResponse)
async def list_change_records(
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
    
    org_id = UUID(current_user.organization_id)
    
    query = select(ChangeRecord).where(ChangeRecord.organization_id == org_id)
    
    if status:
        query = query.where(ChangeRecord.status == status)
    if risk_level:
        query = query.where(ChangeRecord.risk_level == risk_level)
    if device_id:
        query = query.where(ChangeRecord.affected_devices.contains([device_id]))
    if compliance_scope:
        query = query.where(ChangeRecord.affected_compliance_scopes.contains([compliance_scope]))
    
    # Get total count
    count_query = select(func.count()).select_from(ChangeRecord).where(
        ChangeRecord.organization_id == org_id
    )
    if status:
        count_query = count_query.where(ChangeRecord.status == status)
    if risk_level:
        count_query = count_query.where(ChangeRecord.risk_level == risk_level)
    
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # Get paginated results
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
async def get_change_record(
    change_id: str,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific change record"""
    from uuid import UUID
    from sqlalchemy import select
    from fastapi import HTTPException
    
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
async def update_change_record(
    change_id: str,
    change_update: schemas.ChangeRecordUpdate,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a change record (draft/proposed status only)"""
    from uuid import UUID
    from sqlalchemy import select
    from fastapi import HTTPException
    
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
            status_code=400,
            detail=f"Cannot update change in '{change.status}' status"
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
async def delete_change_record(
    change_id: str,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a change record (draft status only)"""
    from uuid import UUID
    from sqlalchemy import select
    from fastapi import HTTPException
    
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
            status_code=400,
            detail="Can only delete change records in draft status"
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
```

---

## Task 3: State Transitions (2b)

### Overview
Implement state machine transitions with role enforcement and audit logging.

### Files
- Modify: `services/api/app/api/routes.py`

### Step 1: Add transition validation helper

**Step 1.1: Add helper function**

Modify: `services/api/app/api/routes.py`

Add after generate_change_number:
```python
VALID_TRANSITIONS = {
    "draft": ["proposed", "deleted"],
    "proposed": ["approved", "draft"],
    "approved": ["scheduled", "in_progress", "rolled_back"],
    "scheduled": ["in_progress", "rolled_back"],
    "in_progress": ["completed", "failed", "rolled_back"],
    "completed": ["rolled_back"],  # Can only rollback completed
    "failed": ["proposed"],  # Can retry from failed
    "rolled_back": [],  # Terminal state
}


def can_transition(current_status: str, new_status: str) -> bool:
    """Check if state transition is valid"""
    return new_status in VALID_TRANSITIONS.get(current_status, [])


# Roles required for transitions
TRANSITION_ROLES = {
    "approve": "admin",
    "verify": "admin",
    "rollback": "admin",
}
```

### Step 2: Add transition endpoints

**Step 2.1: Add propose endpoint**

Modify: `services/api/app/api/routes.py`

Add after DELETE endpoint:
```python
@router.post("/changes/{change_id}/propose", response_model=schemas.ChangeRecordResponse)
async def propose_change(
    change_id: str,
    request: schemas.ChangeProposeRequest,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit change for approval; capture proposed change hash"""
    from uuid import UUID
    from sqlalchemy import select
    from fastapi import HTTPException
    from datetime import datetime
    
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
            status_code=400,
            detail=f"Cannot propose change in '{change.status}' status"
        )
    
    # Validate affected devices populated
    if not change.affected_devices:
        raise HTTPException(
            status_code=400,
            detail="At least one affected device must be specified"
        )
    
    change.status = "proposed"
    change.proposed_change_hash = request.proposed_change_hash
    # Capture pre-change hash from affected devices
    # TODO: Query device config_hash values
    
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


@router.post("/changes/{change_id}/approve", response_model=schemas.ChangeRecordResponse)
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
    
    # Check admin role
    if current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Only administrators can approve changes"
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
            status_code=400,
            detail=f"Cannot approve change in '{change.status}' status"
        )
    
    # Check simulation passed if performed
    if change.simulation_performed and not change.simulation_passed:
        raise HTTPException(
            status_code=400,
            detail="Simulation must pass before approval"
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


@router.post("/changes/{change_id}/implement", response_model=schemas.ChangeRecordResponse)
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
            detail=f"Cannot implement change in '{change.status}' status"
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
async def verify_change(
    change_id: str,
    request: schemas.ChangeVerifyRequest,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify a implemented change (requires admin role)"""
    from uuid import UUID
    from sqlalchemy import select
    from fastapi import HTTPException
    from datetime import datetime
    
    if current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Only administrators can verify changes"
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
            status_code=400,
            detail="Can only verify changes in in_progress status"
        )
    
    change.status = "completed"
    change.verification_results = request.verification_results
    change.verification_passed = request.verification_results.get("passed", False) if request.verification_results else False
    
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


@router.post("/changes/{change_id}/rollback", response_model=schemas.ChangeRecordResponse)
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
    
    if current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Only administrators can rollback changes"
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
            detail=f"Cannot rollback change in '{change.status}' status"
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
```

---

## Task 4: External Ticket Sync (2c)

### Overview
Implement ServiceNow/JIRA integration for ticket creation and webhook receivers.

### Files
- Modify: `services/api/app/api/routes.py`
- Create: `services/api/app/services/ticket_sync.py`

### Step 1: Create ticket sync service

**Step 1.1: Create service file**

Create: `services/api/app/services/ticket_sync.py`

```python
"""
External ticketing system integration service
Supports: ServiceNow, JIRA
"""
import httpx
from typing import Dict, Any
from app.core.config import settings


class TicketSyncService:
    """Service for syncing ChangeRecord to external ticketing systems"""
    
    async def create_servicenow_ticket(
        self,
        change_record: Any,
        integration_config: Any,
    ) -> Dict[str, str]:
        """Create ServiceNow Change Request"""
        base_url = integration_config.base_url
        credentials = self._decrypt_credentials(integration_config.encrypted_credentials)
        
        auth = (credentials.get("username", ""), credentials.get("password", ""))
        
        payload = {
            "short_description": change_record.title,
            "description": change_record.description or "",
            "category": "Network",
            "type": "normal",
            "impact": self._risk_to_impact(change_record.risk_level),
            "urgency": self._risk_to_urgency(change_record.risk_level),
            "state": "1",  # New
            "u_change_type": change_record.change_type,
            "u_requested_by": str(change_record.requested_by),
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{base_url}/api/now/table/change_request",
                auth=auth,
                json=payload,
                timeout=30,
            )
            
            if response.status_code != 201:
                raise Exception(f"ServiceNow API error: {response.text}")
            
            data = response.json()
            result = data.get("result", {})
            
            return {
                "ticket_id": result.get("sys_id", ""),
                "ticket_number": result.get("number", ""),
                "ticket_url": f"{base_url}/change_request.do?sys_id={result.get('sys_id', '')}",
            }
    
    async def create_jira_ticket(
        self,
        change_record: Any,
        integration_config: Any,
    ) -> Dict[str, str]:
        """Create JIRA Issue"""
        base_url = integration_config.base_url
        credentials = self._decrypt_credentials(integration_config.encrypted_credentials)
        
        headers = {
            "Authorization": f"Basic {credentials.get('api_token', '')}",
            "Content-Type": "application/json",
        }
        
        project_key = integration_config.config.get("project_key", "CHANGE")
        
        payload = {
            "fields": {
                "project": {"key": project_key},
                "summary": f"[{change_record.change_number}] {change_record.title}",
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": change_record.description or "",
                                }
                            ],
                        }
                    ],
                },
                "issuetype": {"name": "Task"},
                "priority": {"name": self._risk_to_jira_priority(change_record.risk_level)},
            }
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{base_url}/rest/api/3/issue",
                headers=headers,
                json=payload,
                timeout=30,
            )
            
            if response.status_code != 201:
                raise Exception(f"JIRA API error: {response.text}")
            
            data = response.json()
            
            return {
                "ticket_id": data.get("id", ""),
                "ticket_key": data.get("key", ""),
                "ticket_url": f"{base_url}/browse/{data.get('key', '')}",
            }
    
    def _decrypt_credentials(self, encrypted_credentials: str) -> Dict:
        """Decrypt stored credentials"""
        if not encrypted_credentials:
            return {}
        
        from cryptography.fernet import Fernet
        import json
        
        fernet = Fernet(settings.CREDENTIAL_ENCRYPTION_KEY.encode())
        decrypted = fernet.decrypt(encrypted_credentials.encode()).decode()
        return json.loads(decrypted)
    
    def _risk_to_impact(self, risk_level: str) -> str:
        mapping = {"low": "2", "medium": "2", "high": "1", "critical": "1"}
        return mapping.get(risk_level, "2")
    
    def _risk_to_urgency(self, risk_level: str) -> str:
        mapping = {"low": "4", "medium": "3", "high": "2", "critical": "1"}
        return mapping.get(risk_level, "3")
    
    _risk_to_jira_priority = _risk_to_urgency


ticket_sync_service = TicketSyncService()
```

### Step 2: Add ticket sync endpoints

**Step 2.1: Add sync endpoint**

Modify: `services/api/app/api/routes.py`

Add after rollback endpoint:
```python
@router.post("/changes/{change_id}/sync-ticket", response_model=schemas.ChangeRecordResponse)
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
    
    try:
        change_uuid = UUID(change_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid change ID format")
    
    org_id = UUID(current_user.organization_id)
    
    # Get change record
    result = await db.execute(
        select(ChangeRecord).where(
            ChangeRecord.id == change_uuid,
            ChangeRecord.organization_id == org_id,
        )
    )
    change = result.scalar_one_or_none()
    
    if not change:
        raise HTTPException(status_code=404, detail="Change record not found")
    
    # Get integration config for org
    from app.models.models import IntegrationConfig
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
            detail=f"No enabled {request.ticket_system} integration found"
        )
    
    # Create ticket based on system type
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
                detail=f"Unsupported ticket system: {request.ticket_system}"
            )
        
        change.external_ticket_id = ticket_result.get("ticket_id") or ticket_result.get("ticket_key")
        change.external_ticket_url = ticket_result.get("ticket_url")
        change.ticket_system = request.ticket_system
        
        await db.commit()
        await db.refresh(change)
        
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to create ticket: {str(e)}"
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
    
    try:
        integ_uuid = UUID(integration_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid integration ID")
    
    from app.models.models import IntegrationConfig, ChangeRecord
    
    result = await db.execute(
        select(IntegrationConfig).where(IntegrationConfig.id == integ_uuid)
    )
    integration = result.scalar_one_or_none()
    
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    
    # Process webhook based on ticket system
    if integration.integration_type == "servicenow":
        # ServiceNow webhook - check for approval
        change_request_id = payload.get("sys_id") or payload.get("change_request", {}).get("sys_id")
        state = payload.get("state") or payload.get("change_request", {}).get("state")
        
        if state in ["3", "approved"]:  # Approved states in ServiceNow
            # Find and update ChangeRecord
            cr_result = await db.execute(
                select(ChangeRecord).where(
                    ChangeRecord.external_ticket_id == change_request_id
                )
            )
            change = cr_result.scalar_one_or_none()
            
            if change and change.status == "proposed":
                from datetime import datetime
                # Auto-approve
                change.status = "approved"
                change.approved_at = datetime.utcnow()
                change.approval_notes = f"Auto-approved via ServiceNow webhook"
                await db.commit()
                
    elif integration.integration_type == "jira":
        # JIRA webhook - check for approval transition
        issue_key = payload.get("issue", {}).get("key")
        transition = payload.get("transition", {}).get("name", "").lower()
        
        if "approve" in transition or "resolved" in transition:
            cr_result = await db.execute(
                select(ChangeRecord).where(
                    ChangeRecord.external_ticket_id == issue_key
                )
            )
            change = cr_result.scalar_one_or_none()
            
            if change and change.status == "proposed":
                from datetime import datetime
                change.status = "approved"
                change.approved_at = datetime.utcnow()
                change.approval_notes = f"Auto-approved via JIRA webhook"
                await db.commit()
    
    return {"status": "received"}
```

---

## Task 5: ContainerLab Simulation (2d)

### Overview
Implement ContainerLab simulation trigger endpoint (agent-side implementation separate).

### Files
- Modify: `services/api/app/api/routes.py`

### Step 1: Add simulation endpoints

**Step 1.1: Add simulation endpoints**

Modify: `services/api/app/api/routes.py`

Add after ticket sync endpoint:
```python
@router.post("/changes/{change_id}/simulate", response_model=schemas.ChangeSimulateResponse)
async def trigger_simulation(
    change_id: str,
    request: schemas.ChangeSimulateRequest,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger ContainerLab simulation for a proposed change"""
    from uuid import UUID
    from sqlalchemy import select
    from fastapi import HTTPException
    
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
            status_code=400,
            detail="Can only simulate changes in proposed status"
        )
    
    # Generate simulation ID
    simulation_id = str(uuid4())
    
    # TODO: Queue simulation job to agent via Redis
    # For now, mark as simulation triggered
    change.simulation_performed = True
    # simulation_results will be updated when agent reports back
    
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


@router.get("/changes/{change_id}/simulation-results", response_model=schemas.ChangeRecordResponse)
async def get_simulation_results(
    change_id: str,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get simulation results for a change"""
    from uuid import UUID
    from sqlalchemy import select
    from fastapi import HTTPException
    
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
        simulation_performed=change.simulation_performed,
        simulation_results=change.simulation_results,
        simulation_passed=change.simulation_passed,
        updated_at=change.updated_at,
    )
```

---

## Testing Commands

```bash
# Start services
cd /home/openether/NetDiscoverIT && make up

# Test CRUD
# Create change
curl -X POST http://localhost:8000/api/v1/changes \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "title": "Update ACL on core router",
    "description": "Add new permit rule for DMZ",
    "change_type": "acl_update",
    "risk_level": "high",
    "affected_devices": ["device-uuid-1"]
  }'

# List changes
curl http://localhost:8000/api/v1/changes \
  -H "Authorization: Bearer <token>"

# Propose change
curl -X POST http://localhost:8000/api/v1/changes/{id}/propose \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"proposed_change_hash": "abc123..."}'

# Approve change (requires admin)
curl -X POST http://localhost:8000/api/v1/changes/{id}/approve \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <admin_token>" \
  -d '{"approval_notes": "Approved for maintenance window"}'

# Implement change
curl -X POST http://localhost:8000/api/v1/changes/{id}/implement \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"post_change_hash": "def456..."}'

# Verify change (requires admin)
curl -X POST http://localhost:8000/api/v1/changes/{id}/verify \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <admin_token>" \
  -d '{"verification_results": {"passed": true}}'

# Run tests
pytest services/api/tests/api/test_changes.py -v
```

---

## Dependencies Added

None required - using existing dependencies:
- `httpx` - for ServiceNow/JIRA API calls
- `cryptography` - for credential encryption (already in use)

---

## Estimated Effort

- Task 2a (CRUD): ~3 hours
- Task 2b (State Transitions): ~4 hours
- Task 2c (External Ticket Sync): ~6 hours
- Task 2d (ContainerLab Simulation): ~8 hours (API portion)

**Total: ~21 hours**

---

## Commit Strategy

Commit after each sub-task:
```bash
# After Task 1: Schemas
git add services/api/app/api/schemas.py
git commit -m "feat(api): add ChangeRecord schemas"

# After Task 2: CRUD
git add services/api/app/api/routes.py
git commit -m "feat(api): add ChangeRecord CRUD endpoints"

# After Task 3: State Transitions
git add services/api/app/api/routes.py
git commit -m "feat(api): add ChangeRecord state transition endpoints"

# After Task 4: Ticket Sync
git add services/api/app/api/routes.py services/api/app/services/ticket_sync.py
git commit -m "feat(api): add external ticket sync (ServiceNow/JIRA)"

# After Task 5: ContainerLab
git add services/api/app/api/routes.py
git commit -m "feat(api): add ContainerLab simulation trigger"
```
