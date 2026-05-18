"""
API эндпоинты для управления роботами.

CRUD операции над зарегистрированными роботами с разграничением доступа по пользователям.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models import Network, Robot, RobotStatus, User, UserRole
from app.schemas import (
    ErrorResponse,
    RobotDetailResponse,
    RobotListResponse,
    RobotResponse,
    RobotUpdate,
)

router = APIRouter(prefix="/api/robots", tags=["robots"])


def can_access_robot(robot: Robot, user: User) -> bool:
    """Проверяет, имеет ли пользователь доступ к роботу."""
    if user.role == UserRole.ADMIN:
        return True
    return robot.owner_id == user.id


@router.get(
    "",
    response_model=RobotListResponse,
    summary="Список роботов",
    description="Получение списка роботов текущего пользователя. Админ видит всех роботов.",
)
async def list_robots(
    status_filter: RobotStatus | None = Query(
        None, alias="status", description="Фильтр по статусу"
    ),
    search: str | None = Query(None, description="Поиск по имени или hostname"),
    skip: int = Query(0, ge=0, description="Пропустить записей"),
    limit: int = Query(50, ge=1, le=100, description="Максимум записей"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RobotListResponse:
    """Возвращает список роботов с фильтрацией по владельцу."""
    query = select(Robot)

    if current_user.role != UserRole.ADMIN:
        query = query.where(Robot.owner_id == current_user.id)

    if status_filter:
        query = query.where(Robot.status == status_filter)

    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            (Robot.name.ilike(search_pattern)) | (Robot.hostname.ilike(search_pattern))
        )

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.order_by(Robot.created_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    robots = result.scalars().all()

    return RobotListResponse(
        robots=[RobotResponse.model_validate(r) for r in robots],
        total=total,
    )


@router.get(
    "/{robot_id}",
    response_model=RobotDetailResponse,
    responses={
        403: {"model": ErrorResponse, "description": "Нет доступа к роботу"},
        404: {"model": ErrorResponse, "description": "Робот не найден"},
    },
    summary="Информация о роботе",
    description="Получение детальной информации о роботе по ID.",
)
async def get_robot(
    robot_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RobotDetailResponse:
    """Возвращает информацию о роботе."""
    result = await db.execute(select(Robot).where(Robot.id == robot_id))
    robot = result.scalar_one_or_none()

    if not robot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Робот не найден",
        )

    if not can_access_robot(robot, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к этому роботу",
        )

    return RobotDetailResponse.model_validate(robot)


@router.patch(
    "/{robot_id}",
    response_model=RobotResponse,
    responses={
        403: {"model": ErrorResponse, "description": "Нет доступа к роботу"},
        404: {"model": ErrorResponse, "description": "Робот не найден"},
    },
    summary="Обновление робота",
    description="Частичное обновление информации о роботе.",
)
async def update_robot(
    robot_id: int,
    update_data: RobotUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RobotResponse:
    """Обновляет информацию о роботе."""
    result = await db.execute(select(Robot).where(Robot.id == robot_id))
    robot = result.scalar_one_or_none()

    if not robot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Робот не найден",
        )

    if not can_access_robot(robot, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к этому роботу",
        )

    update_dict = update_data.model_dump(exclude_unset=True)
    if "network_id" in update_dict:
        nid = update_dict["network_id"]
        if nid is not None:
            nr = await db.execute(select(Network).where(Network.id == nid))
            net = nr.scalar_one_or_none()
            if not net:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Сеть не найдена",
                )
            if current_user.role != UserRole.ADMIN and net.owner_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Нет доступа к выбранной сети",
                )

    for field, value in update_dict.items():
        setattr(robot, field, value)

    robot.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(robot)

    return RobotResponse.model_validate(robot)


@router.delete(
    "/{robot_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        403: {"model": ErrorResponse, "description": "Нет доступа к роботу"},
        404: {"model": ErrorResponse, "description": "Робот не найден"},
    },
    summary="Удаление робота",
    description="Удаляет робота из системы мониторинга.",
)
async def delete_robot(
    robot_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Удаляет робота."""
    result = await db.execute(select(Robot).where(Robot.id == robot_id))
    robot = result.scalar_one_or_none()

    if not robot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Робот не найден",
        )

    if not can_access_robot(robot, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к этому роботу",
        )

    await db.delete(robot)
    await db.commit()


@router.post(
    "/{robot_id}/heartbeat",
    response_model=RobotResponse,
    responses={
        403: {"model": ErrorResponse, "description": "Нет доступа к роботу"},
        404: {"model": ErrorResponse, "description": "Робот не найден"},
    },
    summary="Heartbeat робота",
    description="Обновляет время последней активности робота.",
)
async def robot_heartbeat(
    robot_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RobotResponse:
    """Обновляет время последней активности робота."""
    result = await db.execute(select(Robot).where(Robot.id == robot_id))
    robot = result.scalar_one_or_none()

    if not robot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Робот не найден",
        )

    if not can_access_robot(robot, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к этому роботу",
        )

    robot.last_seen_at = datetime.now(UTC)
    if robot.status == RobotStatus.INACTIVE:
        robot.status = RobotStatus.ACTIVE

    await db.commit()
    await db.refresh(robot)

    return RobotResponse.model_validate(robot)
