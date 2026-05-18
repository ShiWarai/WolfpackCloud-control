"""Доп. покрытие deps: allowlist, sync из JWT, inactive user, отсутствие sub."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.config import Settings, get_settings
from app.deps import _sync_user_from_token, _token_matches_control_admin_allowlist, get_optional_current_user
from app.models import User, UserRole


def test_allowlist_empty_returns_false():
    st = Settings(control_admin_usernames="")
    assert _token_matches_control_admin_allowlist({"preferred_username": "a"}, st) is False


def test_allowlist_matches_username_case_insensitive():
    st = Settings(control_admin_usernames="Alice,Bob")
    assert _token_matches_control_admin_allowlist({"preferred_username": "ALICE"}, st) is True


def test_allowlist_matches_email():
    st = Settings(control_admin_usernames="boss@test.local")
    assert _token_matches_control_admin_allowlist({"email": "Boss@test.local"}, st) is True


@pytest.mark.asyncio
async def test_sync_promotes_user_via_allowlist(db_session, make_access_token):
    st = Settings(control_admin_usernames="alice")
    token = make_access_token(
        sub="new-sub",
        preferred_username="alice",
        email="alice@test.local",
        realm_roles=["offline_access"],
    )
    user = await _sync_user_from_token(token, db_session, st)
    assert user.role == UserRole.ADMIN


@pytest.mark.asyncio
async def test_sync_raises_when_sub_missing_raw(jwt_signing_key, db_session):
    st = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "iss": st.keycloak_issuer,
        "iat": now,
        "exp": now + timedelta(hours=1),
        "aud": st.keycloak_audience,
        "email": "x@y.z",
    }
    token = jwt.encode(payload, jwt_signing_key, algorithm="RS256", headers={"kid": "k"})
    with pytest.raises(HTTPException) as ei:
        await _sync_user_from_token(token, db_session, st)
    assert ei.value.status_code == 401


@pytest.mark.asyncio
async def test_sync_raises_inactive_user(db_session, make_access_token):
    st = get_settings()
    token = make_access_token(sub="blocked")
    u = User(
        keycloak_sub="blocked",
        email="blocked@test.local",
        name="B",
        role=UserRole.USER,
        is_active=False,
    )
    db_session.add(u)
    await db_session.commit()

    with pytest.raises(HTTPException) as ei:
        await _sync_user_from_token(token, db_session, st)
    assert ei.value.status_code == 401
    assert "деактивирован" in ei.value.detail


@pytest.mark.asyncio
async def test_sync_updates_role_when_jwt_gains_admin(db_session, make_access_token):
    st = get_settings()
    token_user = make_access_token(sub="grow", realm_roles=[], email="grow@test.local")
    u = await _sync_user_from_token(token_user, db_session, st)
    assert u.role == UserRole.USER

    token_admin = make_access_token(sub="grow", realm_roles=["admin"], email="grow@test.local")
    u2 = await _sync_user_from_token(token_admin, db_session, st)
    assert u2.id == u.id
    assert u2.role == UserRole.ADMIN


@pytest.mark.asyncio
async def test_optional_user_none_without_header(db_session):
    u = await get_optional_current_user(credentials=None, db=db_session)
    assert u is None


@pytest.mark.asyncio
async def test_optional_user_invalid_token_returns_none(db_session):
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="not-a-jwt")
    out = await get_optional_current_user(credentials=creds, db=db_session)
    assert out is None
