"""
Аутентификация: только профиль текущего пользователя (Keycloak выдаёт токены).
"""

from fastapi import APIRouter, Depends

from app.deps import get_current_user
from app.models import User
from app.schemas import UserResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Текущий пользователь",
)
async def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    """Информация о пользователе после синхронизации из Keycloak."""
    return UserResponse.model_validate(current_user)
