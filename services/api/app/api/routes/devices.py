"""
Device routes — CRUD + ML classifier
"""
from uuid import UUID, uuid4
from fastapi import APIRouter, HTTPException, Depends, Request
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from app.api import schemas
from app.api import dependencies
from app.api.dependencies import get_db, get_current_user
from app.models.models import Device, AuditLog
from app.services.role_classifier import RoleClassifier

router = APIRouter()


def _device_response(device_obj: Device) -> schemas.Device:
    """Build a device response with safe timestamp defaults."""
    created_at = getattr(device_obj, "created_at", None) or getattr(device_obj, "discovered_at", None) or datetime.now(timezone.utc)
    updated_at = getattr(device_obj, "updated_at", None) or getattr(device_obj, "last_seen", None) or created_at

    return schemas.Device(
        id=str(device_obj.id),
        hostname=device_obj.hostname,
        management_ip=str(device_obj.ip_address),
        vendor=device_obj.vendor,
        device_type=device_obj.device_type,
        role=device_obj.device_role,
        organization_id=str(device_obj.organization_id),
        created_at=created_at,
        updated_at=updated_at,
    )


def get_classifier() -> RoleClassifier:
    """Get role classifier instance - stateless for rule-based, injectable for testing"""
    return RoleClassifier()


# =============================================================================
# Static routes first — must precede /{device_id} parametric routes
# =============================================================================
@router.post("/classify-batch")
async def batch_classify_devices(
    request: schemas.BatchClassifyRequest,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(dependencies.get_db),
    classifier: RoleClassifier = Depends(get_classifier),
):
    """Batch classify multiple devices - uses bulk query to avoid N+1"""
    stmt = select(Device).where(
        Device.id.in_(request.device_ids),
        Device.organization_id == UUID(current_user.organization_id)
    )
    db_result = await db.execute(stmt)
    devices = {str(d.id): d for d in db_result.scalars().all()}

    results = []
    audit_logs = []

    for device_id in request.device_ids:
        device = devices.get(str(device_id))

        if not device:
            results.append({"device_id": str(device_id), "error": "Not found or not authorized"})
            continue

        # CRITICAL: Use 'meta' column, not 'device_metadata'
        metadata = device.meta or {}
        classification = classifier.classify(metadata)

        old_role = device.inferred_role
        device.inferred_role = classification["inferred_role"]
        device.role_confidence = classification["confidence"]
        device.role_classified_at = classification["classified_at"]
        device.role_classifier_version = "1.0.0"

        results.append({
            "device_id": str(device_id),
            "inferred_role": classification["inferred_role"],
            "confidence": classification["confidence"],
        })

        # Queue AuditLog entry
        audit_logs.append(AuditLog(
            organization_id=UUID(current_user.organization_id),
            user_id=UUID(current_user.id),
            action="device.role_classified",
            resource_type="device",
            resource_id=str(device_id),
            details={
                "old_role": old_role,
                "new_role": classification["inferred_role"],
                "confidence": classification["confidence"],
                "method": classification.get("method"),
                "batch": True,
            },
        ))

    await db.commit()

    # Bulk insert audit logs
    for audit_log in audit_logs:
        db.add(audit_log)
    await db.commit()

    return {"results": results}


# =============================================================================
# Parametric routes
# =============================================================================
@router.get("/", response_model=List[schemas.Device])
async def list_devices(
    skip: int = 0,
    limit: int = 100,
    organization_id: Optional[str] = None,
    current_user: schemas.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all devices for user's organization"""
    org_id = UUID(current_user.organization_id)
    result = await db.execute(
        select(Device).where(Device.organization_id == org_id).offset(skip).limit(limit)
    )
    devices = result.scalars().all()

    await dependencies.audit_log(
        action="device.list",
        resource_type="device",
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return [_device_response(d) for d in devices]


@router.post("/", response_model=schemas.Device, status_code=201)
async def create_device(
    request: Request,
    device: schemas.DeviceCreate,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new device"""
    device_obj = Device(
        id=uuid4(),
        organization_id=UUID(current_user.organization_id),
        hostname=device.hostname,
        ip_address=device.management_ip,
        vendor=device.vendor,
        device_type=device.device_type,
        device_role=device.role,
    )

    db.add(device_obj)
    await db.commit()
    await db.refresh(device_obj)

    await dependencies.audit_log(
        action="device.create",
        resource_type="device",
        resource_id=str(device_obj.id),
        resource_name=device_obj.hostname,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return _device_response(device_obj)


@router.get("/{device_id}", response_model=schemas.Device)
async def get_device(
    device_id: str,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific device"""
    try:
        device_uuid = UUID(device_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid device ID format")

    result = await db.execute(
        select(Device).where(
            Device.id == device_uuid,
            Device.organization_id == UUID(current_user.organization_id),
        )
    )
    device = result.scalar_one_or_none()
    if device is None and hasattr(result, "scalars"):
        scalar_result = result.scalars()
        if hasattr(scalar_result, "first"):
            device = scalar_result.first()

    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    await dependencies.audit_log(
        action="device.view",
        resource_type="device",
        resource_id=device_id,
        resource_name=device.hostname,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return _device_response(device)


@router.patch("/{device_id}", response_model=schemas.Device)
async def update_device(
    request: Request,
    device_id: str,
    device_update: schemas.DeviceUpdate,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a device"""
    try:
        device_uuid = UUID(device_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid device ID format")

    result = await db.execute(
        select(Device).where(
            Device.id == device_uuid,
            Device.organization_id == UUID(current_user.organization_id),
        )
    )
    device = result.scalar_one_or_none()
    if device is None and hasattr(result, "scalars"):
        scalar_result = result.scalars()
        if hasattr(scalar_result, "first"):
            device = scalar_result.first()

    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    update_data = device_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "management_ip":
            setattr(device, "ip_address", value)
        elif field == "role":
            setattr(device, "device_role", value)
        else:
            setattr(device, field, value)

    await db.commit()
    await db.refresh(device)

    await dependencies.audit_log(
        action="device.update",
        resource_type="device",
        resource_id=device_id,
        resource_name=device.hostname,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return _device_response(device)


@router.delete("/{device_id}", status_code=204)
async def delete_device(
    request: Request,
    device_id: str,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a device"""
    try:
        device_uuid = UUID(device_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid device ID format")

    result = await db.execute(
        select(Device).where(
            Device.id == device_uuid,
            Device.organization_id == UUID(current_user.organization_id),
        )
    )
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    await db.delete(device)
    await db.commit()

    await dependencies.audit_log(
        action="device.delete",
        resource_type="device",
        resource_id=device_id,
        resource_name=device.hostname,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return None


@router.post("/{device_id}/classify", response_model=schemas.DeviceClassificationResponse)
async def classify_device(
    device_id: UUID,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(dependencies.get_db),
    classifier: RoleClassifier = Depends(get_classifier),
):
    """Classify device role"""
    result = await db.get(Device, device_id)
    if not result:
        raise HTTPException(status_code=404, detail="Device not found")

    if result.organization_id != UUID(current_user.organization_id):
        raise HTTPException(status_code=403, detail="Not authorized")

    # CRITICAL: Use 'meta' column, not 'device_metadata'
    metadata = result.meta or {}
    classification = classifier.classify(metadata)

    old_role = result.inferred_role
    result.inferred_role = classification["inferred_role"]
    result.role_confidence = classification["confidence"]
    result.role_classified_at = classification["classified_at"]
    result.role_classifier_version = "1.0.0"

    await db.commit()
    await db.refresh(result)

    # Write AuditLog entry for classification
    audit_log = AuditLog(
        organization_id=UUID(current_user.organization_id),
        user_id=UUID(current_user.id),
        action="device.role_classified",
        resource_type="device",
        resource_id=str(device_id),
        details={
            "old_role": old_role,
            "new_role": classification["inferred_role"],
            "confidence": classification["confidence"],
            "method": classification.get("method"),
        },
    )
    db.add(audit_log)
    await db.commit()

    return classification


@router.get("/{device_id}/classification")
async def get_device_classification(
    device_id: UUID,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(dependencies.get_db),
):
    """Get device role classification"""
    result = await db.get(Device, device_id)
    if not result:
        raise HTTPException(status_code=404, detail="Device not found")

    if result.organization_id != UUID(current_user.organization_id):
        raise HTTPException(status_code=403, detail="Not authorized")

    return {
        "inferred_role": result.inferred_role,
        "confidence": result.role_confidence,
        "classified_at": result.role_classified_at,
        "classifier_version": result.role_classifier_version,
    }
