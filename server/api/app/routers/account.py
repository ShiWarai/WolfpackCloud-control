"""Аккаунт пользователя и ссылки на Keycloak."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user
from app.models import Network, User, UserRole
from app.schemas import AccountResponse, NetworkResponse, UserResponse
from app.services.network_stats import robot_counts_by_network_ids

router = APIRouter(prefix="/api/account", tags=["account"])
settings = get_settings()


@router.get("", response_model=AccountResponse)
async def get_account(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AccountResponse:
    if user.role == UserRole.ADMIN:
        q = select(Network).order_by(Network.id.desc())
    else:
        q = select(Network).where(Network.owner_id == user.id).order_by(Network.id.desc())
    result = await db.execute(q)
    nets_raw = result.scalars().all()
    ids = [n.id for n in nets_raw]
    counts = await robot_counts_by_network_ids(db, user, ids)
    nets = [
        NetworkResponse.model_validate(n).model_copy(
            update={"robot_count": counts.get(n.id, 0)}
        )
        for n in nets_raw
    ]
    return AccountResponse(
        user=UserResponse.model_validate(user),
        keycloak_account_url=settings.keycloak_account_console_url,
        networks=nets,
    )
