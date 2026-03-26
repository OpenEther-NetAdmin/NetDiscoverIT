from datetime import datetime
from typing import Dict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import ChangeRecord

async def generate_change_number(db: AsyncSession) -> str:
    """Generate unique change number: CHG-YYYY-NNNN"""
    year = datetime.utcnow().year
    prefix = f"CHG-{year}-"

    result = await db.execute(
        select(func.count())
        .select_from(ChangeRecord)
        .where(ChangeRecord.change_number.like(f"{prefix}%"))
    )
    count = result.scalar() or 0

    return f"{prefix}{count + 1:04d}"


VALID_TRANSITIONS = {
    "draft": ["proposed", "deleted"],
    "proposed": ["approved", "draft"],
    "approved": ["scheduled", "in_progress", "rolled_back"],
    "scheduled": ["in_progress", "rolled_back"],
    "in_progress": ["completed", "failed", "rolled_back"],
    "completed": ["rolled_back"],
    "failed": ["proposed"],
    "rolled_back": [],
}


def can_transition(current_status: str, new_status: str) -> bool:
    """Check if state transition is valid"""
    return new_status in VALID_TRANSITIONS.get(current_status, [])
