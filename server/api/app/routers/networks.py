"""CRUD сетей ROS_DOMAIN_ID."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models import Network, User, UserRole
from app.schemas import NetworkCreate, NetworkResponse, NetworkUpdate
from app.services.network_stats import robot_counts_by_network_ids

router = APIRouter(prefix="/api/networks", tags=["networks"])


@router.get("", response_model=list[NetworkResponse])
async def list_networks(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[NetworkResponse]:
    q = select(Network).order_by(Network.id.desc())
    if user.role != UserRole.ADMIN:
        q = q.where(Network.owner_id == user.id)
    result = await db.execute(q)
    rows = result.scalars().all()
    ids = [n.id for n in rows]
    counts = await robot_counts_by_network_ids(db, user, ids)
    return [
        NetworkResponse.model_validate(n).model_copy(
            update={"robot_count": counts.get(n.id, 0)}
        )
        for n in rows
    ]


@router.post("", response_model=NetworkResponse, status_code=status.HTTP_201_CREATED)
async def create_network(
    body: NetworkCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NetworkResponse:
    net = Network(name=body.name, ros_domain_id=body.ros_domain_id, owner_id=user.id)
    db.add(net)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Сеть с таким ROS_DOMAIN_ID уже существует",
        ) from None
    await db.refresh(net)
    return NetworkResponse.model_validate(net)


@router.patch("/{network_id}", response_model=NetworkResponse)
async def update_network(
    network_id: int,
    body: NetworkUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NetworkResponse:
    result = await db.execute(select(Network).where(Network.id == network_id))
    net = result.scalar_one_or_none()
    if not net:
        raise HTTPException(status_code=404, detail="Сеть не найдена")
    if net.owner_id != user.id and user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Нет доступа")
    if body.name is not None:
        net.name = body.name
    await db.commit()
    await db.refresh(net)
    return NetworkResponse.model_validate(net)


@router.delete("/{network_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_network(
    network_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    result = await db.execute(select(Network).where(Network.id == network_id))
    net = result.scalar_one_or_none()
    if not net:
        raise HTTPException(status_code=404, detail="Сеть не найдена")
    if net.owner_id != user.id and user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Нет доступа")
    await db.delete(net)
    await db.commit()
