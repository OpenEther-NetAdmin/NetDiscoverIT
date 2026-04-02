"""
UserOrgAccess routes — cross-org access grants for MSP users.
"""
from uuid import UUID, uuid4
from typing import List
from fastapi import APIRouter, HTTPException, Depends, status, Request

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import schemas
from app.api import dependencies
from app.api.dependencies import get_db, get_current_user
from app.api.rate_limit import limiter, LIMIT_READ, LIMIT_WRITE
from app.models.models import UserOrgAccess, User

router = APIRouter()


VALID_ACCESS_ROLES = {"read_only", "editor", "admin"}


@router.get("", response_model=schemas.UserOrgAccessListResponse)
@limiter.limit(LIMIT_READ)
async def list_user_org_access(request: Request, 
    skip: int = 0,
    limit: int = 100,
    current_user: schemas.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List all org access grants made BY this organization.
    Only accessible to admin users in the home org.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can view access grants",
        )

    org_id = UUID(current_user.organization_id)

    query = (
        select(UserOrgAccess)
        .join(User, UserOrgAccess.user_id == User.id)
        .where(UserOrgAccess.granted_by == UUID(current_user.id))
        .offset(skip)
        .limit(limit)
    )

    result = await db.execute(query)
    items = result.scalars().all()

    count_result = await db.execute(
        select(func.count()).select_from(UserOrgAccess).where(
            UserOrgAccess.granted_by == UUID(current_user.id)
        )
    )
    total = count_result.scalar() or 0

    return schemas.UserOrgAccessListResponse(
        items=[
            schemas.UserOrgAccessResponse(
                id=str(item.id),
                user_id=str(item.user_id),
                organization_id=str(item.organization_id),
                access_role=item.access_role,
                granted_by=str(item.granted_by) if item.granted_by else None,
                granted_at=item.granted_at,
                expires_at=item.expires_at,
            )
            for item in items
        ],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post("", response_model=schemas.UserOrgAccessResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(LIMIT_WRITE)
async def grant_org_access(request: Request, 
    grant: schemas.UserOrgAccessCreate,
    current_user: schemas.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Grant a user access to an organization.
    Only admin users in the home org can grant access.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can grant org access",
        )

    if grant.access_role not in VALID_ACCESS_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"access_role must be one of: {sorted(VALID_ACCESS_ROLES)}",
        )

    user_result = await db.execute(
        select(User).where(User.id == UUID(grant.user_id))
    )
    target_user = user_result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    existing_result = await db.execute(
        select(UserOrgAccess).where(
            UserOrgAccess.user_id == UUID(grant.user_id),
            UserOrgAccess.organization_id == UUID(grant.organization_id),
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already has access to this organization",
        )

    access = UserOrgAccess(
        id=uuid4(),
        user_id=UUID(grant.user_id),
        organization_id=UUID(grant.organization_id),
        access_role=grant.access_role,
        granted_by=UUID(current_user.id),
    )

    db.add(access)
    await db.commit()
    await db.refresh(access)

    await dependencies.audit_log(
        action="org_access.grant",
        resource_type="user_org_access",
        resource_id=str(access.id),
        resource_name=f"{grant.user_id} -> {grant.organization_id}",
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return schemas.UserOrgAccessResponse(
        id=str(access.id),
        user_id=str(access.user_id),
        organization_id=str(access.organization_id),
        access_role=access.access_role,
        granted_by=str(access.granted_by) if access.granted_by else None,
        granted_at=access.granted_at,
        expires_at=access.expires_at,
    )


@router.get("/{access_id}", response_model=schemas.UserOrgAccessResponse)
@limiter.limit(LIMIT_READ)
async def get_user_org_access(request: Request, 
    access_id: str,
    current_user: schemas.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific org access grant."""
    try:
        access_uuid = UUID(access_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid access ID format")

    result = await db.execute(
        select(UserOrgAccess).where(UserOrgAccess.id == access_uuid)
    )
    access = result.scalar_one_or_none()

    if not access:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access grant not found")

    is_grantee = str(access.user_id) == current_user.id
    is_home_org = access.organization_id == UUID(current_user.organization_id)

    if not is_grantee and not is_home_org:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this grant",
        )

    return schemas.UserOrgAccessResponse(
        id=str(access.id),
        user_id=str(access.user_id),
        organization_id=str(access.organization_id),
        access_role=access.access_role,
        granted_by=str(access.granted_by) if access.granted_by else None,
        granted_at=access.granted_at,
        expires_at=access.expires_at,
    )


@router.patch("/{access_id}", response_model=schemas.UserOrgAccessResponse)
@limiter.limit(LIMIT_WRITE)
async def update_user_org_access(request: Request, 
    access_id: str,
    update: schemas.UserOrgAccessUpdate,
    current_user: schemas.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an org access grant (role or expiry)."""
    try:
        access_uuid = UUID(access_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid access ID format")

    result = await db.execute(
        select(UserOrgAccess).where(UserOrgAccess.id == access_uuid)
    )
    access = result.scalar_one_or_none()

    if not access:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access grant not found")

    if access.organization_id != UUID(current_user.organization_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins in the target org can update this grant",
        )

    if update.access_role is not None:
        if update.access_role not in VALID_ACCESS_ROLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"access_role must be one of: {sorted(VALID_ACCESS_ROLES)}",
            )
        access.access_role = update.access_role

    if update.expires_at is not None:
        access.expires_at = update.expires_at

    await db.commit()
    await db.refresh(access)

    await dependencies.audit_log(
        action="org_access.update",
        resource_type="user_org_access",
        resource_id=str(access.id),
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return schemas.UserOrgAccessResponse(
        id=str(access.id),
        user_id=str(access.user_id),
        organization_id=str(access.organization_id),
        access_role=access.access_role,
        granted_by=str(access.granted_by) if access.granted_by else None,
        granted_at=access.granted_at,
        expires_at=access.expires_at,
    )


@router.delete("/{access_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(LIMIT_WRITE)
async def revoke_org_access(request: Request, 
    access_id: str,
    current_user: schemas.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke an org access grant."""
    try:
        access_uuid = UUID(access_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid access ID format")

    result = await db.execute(
        select(UserOrgAccess).where(UserOrgAccess.id == access_uuid)
    )
    access = result.scalar_one_or_none()

    if not access:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access grant not found")

    if access.organization_id != UUID(current_user.organization_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins in the target org can revoke this grant",
        )

    await db.delete(access)
    await db.commit()

    await dependencies.audit_log(
        action="org_access.revoke",
        resource_type="user_org_access",
        resource_id=str(access.id),
        outcome="success",
        current_user=current_user,
        db=db,
    )
