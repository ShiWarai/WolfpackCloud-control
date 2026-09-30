"""Агрегаты по сетям для UI."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Robot, User, UserRole


async def robot_counts_by_network_ids(
    db: AsyncSession, user: User, network_ids: list[int]
) -> dict[int, int]:
    """Сколько роботов привязано к каждой сети (с учётом прав пользователя)."""
    if not network_ids:
        return {}
    q = (
        select(Robot.network_id, func.count(Robot.id))
        .where(Robot.network_id.in_(network_ids))
        .group_by(Robot.network_id)
    )
    if user.role != UserRole.ADMIN:
        q = q.where(Robot.owner_id == user.id)
    rows = (await db.execute(q)).all()
    out: dict[int, int] = {}
    for nid, cnt in rows:
        if nid is not None:
            out[int(nid)] = int(cnt)
    return out
