"""
API эндпоинты для привязки роботов.

Обеспечивает регистрацию роботов через 8-значный код и подтверждение привязки.
"""

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user
from app.models import PairCode, PairCodeStatus, Robot, RobotStatus, User
from app.schemas import (
    ErrorResponse,
    PairCodeInfoResponse,
    PairConfirmRequest,
    PairConfirmResponse,
    PairRequest,
    PairResponse,
    PairStatusResponse,
)

router = APIRouter(prefix="/api/pair", tags=["pairing"])
settings = get_settings()


def generate_influxdb_token() -> str:
    """Генерирует токен для InfluxDB."""
    return secrets.token_urlsafe(32)


@router.post(
    "",
    response_model=PairResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse, "description": "Неверный запрос"},
        409: {"model": ErrorResponse, "description": "Код привязки уже используется"},
    },
    summary="Регистрация робота",
    description="Вызывается агентом на роботе для регистрации в системе мониторинга.",
)
async def register_robot(
    request: PairRequest,
    db: AsyncSession = Depends(get_db),
) -> PairResponse:
    """
    Регистрирует робота в системе.

    Агент на роботе вызывает этот эндпоинт, передавая сгенерированный 8-значный код.
    Робот создаётся в статусе PENDING и ожидает подтверждения пользователем.
    """
    # Проверяем, не занят ли код
    existing = await db.execute(
        select(PairCode).where(
            PairCode.code == request.pair_code,
            PairCode.status == PairCodeStatus.PENDING,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Код привязки уже используется",
        )

    # Создаём робота
    robot = Robot(
        name=request.name or request.hostname,
        hostname=request.hostname,
        ip_address=request.ip_address,
        architecture=request.architecture,
        status=RobotStatus.PENDING,
    )
    db.add(robot)
    await db.flush()

    # Создаём код привязки
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.pair_code_expiration_minutes)
    pair_code = PairCode(
        code=request.pair_code,
        robot_id=robot.id,
        status=PairCodeStatus.PENDING,
        expires_at=expires_at,
    )
    db.add(pair_code)
    await db.commit()

    return PairResponse(
        robot_id=robot.id,
        pair_code=request.pair_code,
        status=PairCodeStatus.PENDING,
        expires_at=expires_at,
        influxdb_token=None,
        message=f"Робот зарегистрирован. Код привязки: {request.pair_code}. "
        f"Подтвердите привязку в панели управления в течение {settings.pair_code_expiration_minutes} минут.",
    )


@router.get(
    "/{code}",
    response_model=PairCodeInfoResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Код не найден"},
    },
    summary="Информация о коде привязки",
    description="Получение информации о коде привязки и связанном роботе.",
)
async def get_pair_code_info(
    code: str,
    db: AsyncSession = Depends(get_db),
) -> PairCodeInfoResponse:
    """Получает информацию о коде привязки."""
    result = await db.execute(
        select(PairCode).options(selectinload(PairCode.robot)).where(PairCode.code == code.upper())
    )
    pair_code = result.scalar_one_or_none()

    if not pair_code:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Код привязки не найден",
        )

    # Проверяем истечение срока
    if pair_code.status == PairCodeStatus.PENDING and pair_code.expires_at < datetime.now(UTC):
        pair_code.status = PairCodeStatus.EXPIRED
        await db.commit()

    return PairCodeInfoResponse.model_validate(pair_code)


@router.get(
    "/{code}/status",
    response_model=PairStatusResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Код не найден"},
    },
    summary="Статус привязки (для polling)",
    description="""
Возвращает статус привязки. Используется агентом для polling после регистрации.

После подтверждения привязки возвращает токен для отправки метрик.
    """,
)
async def get_pair_status(
    code: str,
    db: AsyncSession = Depends(get_db),
) -> PairStatusResponse:
    """
    Возвращает статус привязки для агента.

    Агент вызывает этот эндпоинт периодически после регистрации,
    чтобы узнать, подтверждена ли привязка и получить токен.
    """
    result = await db.execute(
        select(PairCode).options(selectinload(PairCode.robot)).where(PairCode.code == code.upper())
    )
    pair_code = result.scalar_one_or_none()

    if not pair_code:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Код привязки не найден",
        )

    # Проверяем истечение срока
    if pair_code.status == PairCodeStatus.PENDING and pair_code.expires_at < datetime.now(UTC):
        pair_code.status = PairCodeStatus.EXPIRED
        await db.commit()

    robot = pair_code.robot

    if pair_code.status == PairCodeStatus.CONFIRMED:
        return PairStatusResponse(
            status=pair_code.status,
            robot_id=robot.id,
            robot_token=robot.influxdb_token,
            api_url=f"{settings.api_base_url}/api/metrics",
            message="Привязка подтверждена. Используйте токен для отправки метрик.",
        )
    elif pair_code.status == PairCodeStatus.EXPIRED:
        return PairStatusResponse(
            status=pair_code.status,
            robot_id=None,
            robot_token=None,
            api_url=settings.api_base_url,
            message="Срок действия кода истёк. Зарегистрируйтесь заново.",
        )
    else:
        return PairStatusResponse(
            status=pair_code.status,
            robot_id=robot.id,
            robot_token=None,
            api_url=settings.api_base_url,
            message="Ожидание подтверждения пользователем.",
        )


@router.post(
    "/{code}/confirm",
    response_model=PairConfirmResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Невозможно подтвердить"},
        401: {"model": ErrorResponse, "description": "Требуется авторизация"},
        404: {"model": ErrorResponse, "description": "Код не найден"},
        410: {"model": ErrorResponse, "description": "Код истёк"},
    },
    summary="Подтверждение привязки",
    description="Подтверждает привязку робота к текущему пользователю. Требуется авторизация.",
)
async def confirm_pairing(
    code: str,
    request: PairConfirmRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PairConfirmResponse:
    """
    Подтверждает привязку робота к текущему пользователю.

    После подтверждения:
    - Робот привязывается к текущему пользователю (owner_id)
    - Статус робота меняется на ACTIVE
    - Генерируется токен InfluxDB для отправки метрик
    - Код привязки помечается как CONFIRMED
    """
    result = await db.execute(
        select(PairCode).options(selectinload(PairCode.robot)).where(PairCode.code == code.upper())
    )
    pair_code = result.scalar_one_or_none()

    if not pair_code:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Код привязки не найден",
        )

    if pair_code.status == PairCodeStatus.CONFIRMED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Код уже был подтверждён",
        )

    if pair_code.status == PairCodeStatus.EXPIRED or pair_code.expires_at < datetime.now(UTC):
        pair_code.status = PairCodeStatus.EXPIRED
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Срок действия кода истёк",
        )

    influxdb_token = generate_influxdb_token()

    robot = pair_code.robot
    if request and request.robot_name:
        robot.name = request.robot_name
    robot.status = RobotStatus.ACTIVE
    robot.influxdb_token = influxdb_token
    robot.last_seen_at = datetime.now(UTC)
    robot.owner_id = current_user.id

    pair_code.status = PairCodeStatus.CONFIRMED
    pair_code.confirmed_at = datetime.now(UTC)

    await db.commit()

    return PairConfirmResponse(
        robot_id=robot.id,
        status=robot.status,
        influxdb_token=influxdb_token,
        message=f"Робот '{robot.name}' успешно привязан к пользователю {current_user.name}.",
    )
