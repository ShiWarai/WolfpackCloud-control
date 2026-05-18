"""SQLite test DB, JWKS stub, scheduler noop, ASGI client, JWT helpers."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

import jwt
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from jwt import PyJWKClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("KEYCLOAK_ISSUER", "http://test.keycloak.invalid/realms/wolfpack")
os.environ.setdefault(
    "KEYCLOAK_JWKS_URL",
    "http://test.keycloak.invalid/realms/wolfpack/protocol/openid-connect/certs",
)
os.environ.setdefault("KEYCLOAK_AUDIENCE", "wolfpack-control-web")

from app.config import Settings, get_settings  # noqa: E402

get_settings.cache_clear()


def mint_access_token(
    *,
    private_key: Any,
    settings: Settings,
    sub: str = "user-1",
    email: str = "user@example.com",
    preferred_username: str = "user",
    realm_roles: list[str] | None = None,
    resource_access: dict[str, Any] | None = None,
    audience: str | None = "wolfpack-control-web",
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": sub,
        "email": email,
        "preferred_username": preferred_username,
        "iss": settings.keycloak_issuer,
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    if audience is not None:
        payload["aud"] = audience
    if realm_roles is not None:
        payload["realm_access"] = {"roles": realm_roles}
    if resource_access:
        payload["resource_access"] = resource_access
    return jwt.encode(
        payload,
        private_key,
        algorithm="RS256",
        headers={"kid": "test-kid"},
    )


@pytest.fixture(scope="session")
def rsa_test_keys() -> tuple[Any, Any]:
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return priv, priv.public_key()


@pytest.fixture(scope="session")
def jwt_signing_key(rsa_test_keys: tuple[Any, Any]) -> Any:
    return rsa_test_keys[0]


@pytest.fixture(scope="session")
def jwk_patch(rsa_test_keys: tuple[Any, Any]):
    _, public_key = rsa_test_keys

    class _Key:
        key = public_key

    def _fake_get_signing_key_from_jwt(_self: PyJWKClient, _jwt: str) -> _Key:
        return _Key()

    with patch.object(PyJWKClient, "get_signing_key_from_jwt", _fake_get_signing_key_from_jwt):
        yield


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _session_db_and_scheduler(jwk_patch):  # noqa: ARG001
    from app.database import Base, engine
    from app.tasks import scheduler

    sched_patch = patch.multiple(
        scheduler,
        add_job=lambda *a, **k: None,
        start=lambda: None,
        shutdown=lambda wait=False: None,
    )
    sched_patch.start()
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield
    finally:
        sched_patch.stop()


@pytest.fixture
def make_access_token(jwt_signing_key: Any):
    def _make(**kwargs: Any) -> str:
        return mint_access_token(private_key=jwt_signing_key, settings=get_settings(), **kwargs)

    return _make


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def db_session():
    from app.database import async_session_maker

    async with async_session_maker() as session:
        yield session
