"""
Приём «метрик» / heartbeat без InfluxDB (MVP): обновляет last_seen робота по токену.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Robot, RobotStatus

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


async def get_robot_by_token(
    authorization: str = Header(..., description="Bearer {robot_token}"),
    db: AsyncSession = Depends(get_db),
) -> Robot:
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ожидается Authorization: Bearer <token>",
        )

    token = authorization[7:]
    result = await db.execute(select(Robot).where(Robot.influxdb_token == token))
    robot = result.scalar_one_or_none()

    if not robot:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Невалидный токен")

    if robot.status != RobotStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Робот не активен: {robot.status}",
        )

    return robot


@router.post(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Heartbeat робота (метрики отключены в Control MVP)",
)
async def ingest_metrics(
    request: Request,
    robot: Robot = Depends(get_robot_by_token),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Тело запроса игнорируется; обновляется last_seen_at."""
    await request.body()
    robot.last_seen_at = datetime.now(timezone.utc)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
