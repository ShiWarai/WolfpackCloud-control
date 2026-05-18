"""Чтение кэша rosout для UI."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models import RosLogEntry, User
from app.schemas import RosLogEntryResponse

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("", response_model=list[RosLogEntryResponse])
async def list_logs(
    network_id: int | None = Query(None),
    limit: int = Query(200, ge=1, le=2000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[RosLogEntryResponse]:
    q = select(RosLogEntry).order_by(RosLogEntry.recorded_at.desc()).limit(limit)
    if network_id is not None:
        # rosout-bridge по умолчанию шлёт network_id=null — без этого фильтр «глотается»
        q = q.where(
            or_(
                RosLogEntry.network_id == network_id,
                RosLogEntry.network_id.is_(None),
            )
        )
    result = await db.execute(q)
    rows = result.scalars().all()
    return [RosLogEntryResponse.model_validate(r) for r in rows]
