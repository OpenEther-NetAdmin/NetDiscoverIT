"""Sites routes"""
from uuid import UUID
from typing import List
from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import schemas
from app.api import dependencies
from app.api.dependencies import get_db, get_current_user, get_rate_limit
from app.models.models import Site

router = APIRouter()


def _site_response(site_obj: Site) -> schemas.SiteResponse:
    """Build a site response with safe timestamp defaults."""
    from datetime import datetime, timezone

    created_at = site_obj.created_at or datetime.now(timezone.utc)
    updated_at = site_obj.updated_at or created_at

    return schemas.SiteResponse(
        id=str(site_obj.id),
        name=site_obj.name,
        description=site_obj.description,
        site_type=site_obj.site_type,
        location_address=site_obj.location_address,
        timezone=site_obj.timezone,
        organization_id=str(site_obj.organization_id),
        is_active=site_obj.is_active,
        created_at=created_at,
        updated_at=updated_at,
    )


@router.get("", response_model=List[schemas.SiteResponse])
async def list_sites(
    skip: int = 0,
    limit: int = 100,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all sites for user's organization"""
    from uuid import UUID

    org_id = UUID(current_user.organization_id)
    result = await db.execute(
        select(Site).where(Site.organization_id == org_id).offset(skip).limit(limit)
    )
    sites = result.scalars().all()

    await dependencies.audit_log(
        action="site.list",
        resource_type="site",
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return [
        schemas.SiteResponse(
            id=str(s.id),
            name=s.name,
            description=s.description,
            site_type=s.site_type,
            location_address=s.location_address,
            timezone=s.timezone,
            organization_id=str(s.organization_id),
            is_active=s.is_active,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in sites
    ]


@router.get("/{site_id}", response_model=schemas.SiteResponse)
async def get_site(
    site_id: str,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific site"""
    from uuid import UUID

    try:
        site_uuid = UUID(site_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid site ID format")

    result = await db.execute(
        select(Site).where(
            Site.id == site_uuid,
            Site.organization_id == UUID(current_user.organization_id),
        )
    )
    site = result.scalar_one_or_none()
    if site is None and hasattr(result, "scalars"):
        scalar_result = result.scalars()
        if hasattr(scalar_result, "first"):
            site = scalar_result.first()

    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    await dependencies.audit_log(
        action="site.view",
        resource_type="site",
        resource_id=site_id,
        resource_name=site.name,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return _site_response(site)


@router.post("", response_model=schemas.SiteResponse, status_code=201)
async def create_site(
    site: schemas.SiteCreate,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new site"""
    from uuid import UUID, uuid4

    site_obj = Site(
        id=uuid4(),
        organization_id=UUID(current_user.organization_id),
        name=site.name,
        description=site.description,
        site_type=site.site_type,
        location_address=site.location_address,
        timezone=site.timezone,
        is_active=True,
    )

    db.add(site_obj)
    await db.commit()
    await db.refresh(site_obj)

    await dependencies.audit_log(
        action="site.create",
        resource_type="site",
        resource_id=str(site_obj.id),
        resource_name=site_obj.name,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return _site_response(site_obj)


@router.patch("/{site_id}", response_model=schemas.SiteResponse)
async def update_site(
    site_id: str,
    site_update: schemas.SiteUpdate,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a site"""
    from uuid import UUID

    try:
        site_uuid = UUID(site_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid site ID format")

    result = await db.execute(
        select(Site).where(
            Site.id == site_uuid,
            Site.organization_id == UUID(current_user.organization_id),
        )
    )
    site = result.scalar_one_or_none()
    if site is None and hasattr(result, "scalars"):
        scalar_result = result.scalars()
        if hasattr(scalar_result, "first"):
            site = scalar_result.first()

    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    update_data = site_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(site, field, value)

    await db.commit()
    await db.refresh(site)

    await dependencies.audit_log(
        action="site.update",
        resource_type="site",
        resource_id=site_id,
        resource_name=site.name,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return _site_response(site)


@router.delete("/{site_id}", status_code=204)
async def delete_site(
    site_id: str,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a site"""
    from uuid import UUID

    try:
        site_uuid = UUID(site_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid site ID format")

    result = await db.execute(
        select(Site).where(
            Site.id == site_uuid,
            Site.organization_id == UUID(current_user.organization_id),
        )
    )
    site = result.scalar_one_or_none()

    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    await db.delete(site)
    await db.commit()

    await dependencies.audit_log(
        action="site.delete",
        resource_type="site",
        resource_id=site_id,
        resource_name=site.name,
        outcome="success",
        current_user=current_user,
        db=db,
    )

    return None
