"""
ACL Snapshot routes — Compliance Vault
"""
from uuid import UUID
from fastapi import APIRouter, HTTPException, Depends, status, Request
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import schemas
from app.api import dependencies
from app.api.dependencies import get_db, get_current_user, get_agent_auth
from app.api.rate_limit import limiter, LIMIT_READ, LIMIT_WRITE
from app.models.models import ACLSnapshot

router = APIRouter()


# =============================================================================
# ACL SNAPSHOTS (Compliance Vault)
# =============================================================================
@router.post(
    "",
    response_model=schemas.ACLSnapshotResponse,
    status_code=201,
)
@limiter.limit(LIMIT_WRITE)
async def create_acl_snapshot(
    request: Request,
    snapshot_data: schemas.ACLSnapshotCreate,
    db: AsyncSession = Depends(get_db),
    agent: schemas.AgentAuth = Depends(get_agent_auth),
):
    """Create a new ACL snapshot (agent-authenticated)"""
    from app.models.models import Organization

    org_result = await db.execute(
        select(Organization).where(Organization.id == UUID(agent.organization_id))
    )
    organization = org_result.scalar_one_or_none()
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")

    snapshot = ACLSnapshot(
        organization_id=UUID(agent.organization_id),
        device_id=UUID(snapshot_data.device_id),
        content_type=snapshot_data.content_type,
        encrypted_blob=snapshot_data.encrypted_blob,
        content_hmac=snapshot_data.content_hmac,
        plaintext_size_bytes=snapshot_data.plaintext_size_bytes,
        key_id=snapshot_data.key_id,
        key_provider=snapshot_data.key_provider,
        config_hash_at_capture=snapshot_data.config_hash_at_capture,
        compliance_scope=snapshot_data.compliance_scope,
    )
    db.add(snapshot)
    await db.commit()
    await db.refresh(snapshot)

    return schemas.ACLSnapshotResponse(
        id=str(snapshot.id),
        organization_id=str(snapshot.organization_id),
        device_id=str(snapshot.device_id),
        content_type=snapshot.content_type,
        encrypted_blob=snapshot.encrypted_blob,
        content_hmac=snapshot.content_hmac,
        plaintext_size_bytes=snapshot.plaintext_size_bytes,
        key_id=snapshot.key_id,
        key_provider=snapshot.key_provider,
        encryption_algorithm=snapshot.encryption_algorithm,
        captured_at=snapshot.captured_at,
        captured_by=str(snapshot.captured_by) if snapshot.captured_by else None,
        config_hash_at_capture=snapshot.config_hash_at_capture,
        compliance_scope=snapshot.compliance_scope or [],
        created_at=snapshot.created_at,
    )


@router.get("", response_model=schemas.ACLSnapshotListResponse)
@limiter.limit(LIMIT_READ)
async def list_acl_snapshots(
    request: Request,
    skip: int = 0,
    limit: int = 100,
    device_id: Optional[str] = None,
    content_type: Optional[str] = None,
    current_user: schemas.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List ACL snapshots for user's organization"""
    org_id = UUID(current_user.organization_id)

    query = select(ACLSnapshot).where(ACLSnapshot.organization_id == org_id)

    if device_id:
        query = query.where(ACLSnapshot.device_id == UUID(device_id))
    if content_type:
        query = query.where(ACLSnapshot.content_type == content_type)

    query = query.order_by(ACLSnapshot.captured_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    snapshots = result.scalars().all()

    count_query = select(ACLSnapshot).where(ACLSnapshot.organization_id == org_id)
    if device_id:
        count_query = count_query.where(ACLSnapshot.device_id == UUID(device_id))
    if content_type:
        count_query = count_query.where(ACLSnapshot.content_type == content_type)

    total_result = await db.execute(count_query)
    total = len(total_result.scalars().all())

    return schemas.ACLSnapshotListResponse(
        items=[
            schemas.ACLSnapshotResponse(
                id=str(s.id),
                organization_id=str(s.organization_id),
                device_id=str(s.device_id),
                content_type=s.content_type,
                encrypted_blob=s.encrypted_blob,
                content_hmac=s.content_hmac,
                plaintext_size_bytes=s.plaintext_size_bytes,
                key_id=s.key_id,
                key_provider=s.key_provider,
                encryption_algorithm=s.encryption_algorithm,
                captured_at=s.captured_at,
                captured_by=str(s.captured_by) if s.captured_by else None,
                config_hash_at_capture=s.config_hash_at_capture,
                compliance_scope=s.compliance_scope or [],
                created_at=s.created_at,
            )
            for s in snapshots
        ],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{snapshot_id}", response_model=schemas.ACLSnapshotResponse)
@limiter.limit(LIMIT_READ)
async def get_acl_snapshot(
    request: Request,
    snapshot_id: str,
    current_user: schemas.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific ACL snapshot"""
    try:
        snapshot_uuid = UUID(snapshot_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid snapshot ID format")

    result = await db.execute(
        select(ACLSnapshot).where(
            ACLSnapshot.id == snapshot_uuid,
            ACLSnapshot.organization_id == UUID(current_user.organization_id),
        )
    )
    snapshot = result.scalar_one_or_none()

    if not snapshot:
        raise HTTPException(status_code=404, detail="ACL snapshot not found")

    return schemas.ACLSnapshotResponse(
        id=str(snapshot.id),
        organization_id=str(snapshot.organization_id),
        device_id=str(snapshot.device_id),
        content_type=snapshot.content_type,
        encrypted_blob=snapshot.encrypted_blob,
        content_hmac=snapshot.content_hmac,
        plaintext_size_bytes=snapshot.plaintext_size_bytes,
        key_id=snapshot.key_id,
        key_provider=snapshot.key_provider,
        encryption_algorithm=snapshot.encryption_algorithm,
        captured_at=snapshot.captured_at,
        captured_by=str(snapshot.captured_by) if snapshot.captured_by else None,
        config_hash_at_capture=snapshot.config_hash_at_capture,
        compliance_scope=snapshot.compliance_scope or [],
        created_at=snapshot.created_at,
    )


@router.delete("/{snapshot_id}", status_code=204)
@limiter.limit(LIMIT_WRITE)
async def delete_acl_snapshot(
    request: Request,
    snapshot_id: str,
    current_user: schemas.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an ACL snapshot"""
    try:
        snapshot_uuid = UUID(snapshot_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid snapshot ID format")

    result = await db.execute(
        select(ACLSnapshot).where(
            ACLSnapshot.id == snapshot_uuid,
            ACLSnapshot.organization_id == UUID(current_user.organization_id),
        )
    )
    snapshot = result.scalar_one_or_none()

    if not snapshot:
        raise HTTPException(status_code=404, detail="ACL snapshot not found")

    await db.delete(snapshot)
    await db.commit()


@router.patch(
    "/{snapshot_id}", response_model=schemas.ACLSnapshotResponse
)
@limiter.limit(LIMIT_WRITE)
async def update_acl_snapshot(
    request: Request,
    snapshot_id: str,
    snapshot_data: schemas.ACLSnapshotUpdate,
    current_user: schemas.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an ACL snapshot (e.g., compliance_scope)"""
    try:
        snapshot_uuid = UUID(snapshot_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid snapshot ID format")

    result = await db.execute(
        select(ACLSnapshot).where(
            ACLSnapshot.id == snapshot_uuid,
            ACLSnapshot.organization_id == UUID(current_user.organization_id),
        )
    )
    snapshot = result.scalar_one_or_none()

    if not snapshot:
        raise HTTPException(status_code=404, detail="ACL snapshot not found")

    if snapshot_data.compliance_scope is not None:
        snapshot.compliance_scope = snapshot_data.compliance_scope

    await db.commit()
    await db.refresh(snapshot)

    return schemas.ACLSnapshotResponse(
        id=str(snapshot.id),
        organization_id=str(snapshot.organization_id),
        device_id=str(snapshot.device_id),
        content_type=snapshot.content_type,
        encrypted_blob=snapshot.encrypted_blob,
        content_hmac=snapshot.content_hmac,
        plaintext_size_bytes=snapshot.plaintext_size_bytes,
        key_id=snapshot.key_id,
        key_provider=snapshot.key_provider,
        encryption_algorithm=snapshot.encryption_algorithm,
        captured_at=snapshot.captured_at,
        captured_by=str(snapshot.captured_by) if snapshot.captured_by else None,
        config_hash_at_capture=snapshot.config_hash_at_capture,
        compliance_scope=snapshot.compliance_scope or [],
        created_at=snapshot.created_at,
    )


@router.get("/{snapshot_id}/verify", response_model=schemas.ACLVerifyResult)
@limiter.limit(LIMIT_READ)
async def verify_acl_snapshot(
    request: Request,
    snapshot_id: str,
    current_user: schemas.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Verify the integrity of an ACL snapshot.

    Checks performed:
    - org ownership (user must have access to the snapshot's org)
    - snapshot exists and is accessible
    - content_hmac is present (HMAC integrity marker)
    - config_hash_at_capture is present (configuration hash at capture time)
    - plaintext_size_bytes is non-zero (blob is not empty)
    """
    try:
        snapshot_uuid = UUID(snapshot_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid snapshot ID format")

    result = await db.execute(
        select(ACLSnapshot).where(ACLSnapshot.id == snapshot_uuid)
    )
    snapshot = result.scalar_one_or_none()

    if not snapshot:
        raise HTTPException(status_code=404, detail="ACL snapshot not found")

    try:
        await dependencies.require_org_access(str(snapshot.organization_id), current_user, db)
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this snapshot",
        )

    checks = {}
    all_passed = True

    checks["org_ownership"] = {
        "passed": True,
        "detail": f"Snapshot belongs to org {snapshot.organization_id}",
    }

    if snapshot.content_hmac:
        checks["content_hmac_present"] = {
            "passed": True,
            "detail": "HMAC integrity marker is present",
        }
    else:
        checks["content_hmac_present"] = {
            "passed": False,
            "detail": "HMAC integrity marker is missing — snapshot may have been tampered with",
        }
        all_passed = False

    if snapshot.config_hash_at_capture:
        checks["config_hash_present"] = {
            "passed": True,
            "detail": f"Config hash present: {snapshot.config_hash_at_capture[:12]}...",
        }
    else:
        checks["config_hash_present"] = {
            "passed": False,
            "detail": "Config hash at capture is missing",
        }
        all_passed = False

    if snapshot.plaintext_size_bytes and snapshot.plaintext_size_bytes > 0:
        checks["non_empty_blob"] = {
            "passed": True,
            "detail": f"Blob size: {snapshot.plaintext_size_bytes} bytes",
        }
    else:
        checks["non_empty_blob"] = {
            "passed": False,
            "detail": "Blob is empty or size is zero",
        }
        all_passed = False

    if snapshot.key_id and snapshot.key_provider:
        checks["key_info_present"] = {
            "passed": True,
            "detail": f"Key provider: {snapshot.key_provider}, key ID: {snapshot.key_id}",
        }
    else:
        checks["key_info_present"] = {
            "passed": False,
            "detail": "Key ID or key provider is missing",
        }
        all_passed = False

    if not all_passed:
        failed_checks = [k for k, v in checks.items() if not v["passed"]]
        checks["summary"] = {
            "passed": False,
            "detail": f"Verification failed. Failed checks: {', '.join(failed_checks)}",
        }
    else:
        checks["summary"] = {
            "passed": True,
            "detail": "All verification checks passed",
        }

    return schemas.ACLVerifyResult(
        snapshot_id=str(snapshot.id),
        verified=all_passed,
        checks=checks,
    )

