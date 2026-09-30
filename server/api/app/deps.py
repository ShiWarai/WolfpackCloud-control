"""
Зависимости FastAPI: Keycloak JWT + синхронизация пользователя в БД.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db
from app.models import User, UserRole
from app.services.keycloak_jwt import (
    decode_keycloak_access_token,
    effective_roles_from_payload,
)

settings = get_settings()
security = HTTPBearer()


def _token_matches_control_admin_allowlist(payload: dict, st: Settings) -> bool:
    allow = st.control_admin_identities_lower
    if not allow:
        return False
    uname = (payload.get("preferred_username") or "").strip().lower()
    email = (payload.get("email") or "").strip().lower()
    return bool(uname and uname in allow) or bool(email and email in allow)


async def _sync_user_from_token(token: str, db: AsyncSession, st: Settings) -> User:
    payload = decode_keycloak_access_token(token, st)
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный токен авторизации",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(select(User).where(User.keycloak_sub == sub))
    user = result.scalar_one_or_none()

    roles = effective_roles_from_payload(payload)
    role_from_token = UserRole.ADMIN if "admin" in roles else UserRole.USER
    if role_from_token != UserRole.ADMIN and _token_matches_control_admin_allowlist(payload, st):
        role_from_token = UserRole.ADMIN

    if user:
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Аккаунт деактивирован")
        if user.role != role_from_token:
            user.role = role_from_token
            await db.commit()
            await db.refresh(user)
        return user

    email = (payload.get("email") or payload.get("preferred_username") or f"kc-{sub}@local")[:255]
    name_raw = payload.get("name") or payload.get("preferred_username") or email
    name = str(name_raw)[:255]

    user = User(
        keycloak_sub=sub,
        email=email.lower(),
        name=name,
        hashed_password=None,
        role=role_from_token,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Текущий пользователь по Bearer-токену Keycloak."""
    try:
        return await _sync_user_from_token(credentials.credentials, db, settings)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный токен авторизации",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None


async def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав. Требуется роль администратора.",
        )
    return current_user


async def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    if credentials is None:
        return None
    try:
        return await _sync_user_from_token(credentials.credentials, db, settings)
    except Exception:
        return None
