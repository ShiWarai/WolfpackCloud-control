"""Мок httpx для ExternalAuthService (Grafana / Superset)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.external_auth import ExternalAuthService


class _ExtSettings:
    grafana_url = "http://grafana.test"
    grafana_admin_user = "ga"
    grafana_admin_password = "gp"
    superset_url = "http://superset.test"
    superset_admin_username = "sa"
    superset_admin_password = "sp"


def _make_resp(status: int, data: dict | None = None, text: str = "") -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.text = text
    if data is not None:
        r.json.return_value = data
    return r


def _client_cm(inner: MagicMock):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=inner)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


@pytest.mark.asyncio
async def test_grafana_create_user_success():
    inner_post = MagicMock()
    inner_post.post = AsyncMock(return_value=_make_resp(200, {"id": 42}))
    inner_patch = MagicMock()
    inner_patch.patch = AsyncMock(return_value=_make_resp(200, {}))

    inners = [inner_post, inner_patch]

    def factory(**kwargs):
        return _client_cm(inners.pop(0))

    with patch("app.services.external_auth.httpx.AsyncClient", side_effect=factory):
        svc = ExternalAuthService(_ExtSettings())
        uid = await svc.create_grafana_user("bob@test.org", "pw", "Bob")
        assert uid == 42


@pytest.mark.asyncio
async def test_grafana_create_non_200_returns_none():
    inner = MagicMock()
    inner.post = AsyncMock(return_value=_make_resp(500, text="err"))

    with patch("app.services.external_auth.httpx.AsyncClient", side_effect=lambda **kw: _client_cm(inner)):
        svc = ExternalAuthService(_ExtSettings())
        assert await svc.create_grafana_user("a@b.c", "p", "N") is None


@pytest.mark.asyncio
async def test_grafana_create_missing_user_id_returns_none():
    inner = MagicMock()
    inner.post = AsyncMock(return_value=_make_resp(200, {}))

    with patch("app.services.external_auth.httpx.AsyncClient", side_effect=lambda **kw: _client_cm(inner)):
        svc = ExternalAuthService(_ExtSettings())
        assert await svc.create_grafana_user("a@b.c", "p", "N") is None


@pytest.mark.asyncio
async def test_grafana_delete_success():
    inner = MagicMock()
    inner.delete = AsyncMock(return_value=_make_resp(200))

    with patch("app.services.external_auth.httpx.AsyncClient", side_effect=lambda **kw: _client_cm(inner)):
        svc = ExternalAuthService(_ExtSettings())
        assert await svc.delete_grafana_user(7) is True


@pytest.mark.asyncio
async def test_grafana_delete_404_still_true():
    inner = MagicMock()
    inner.delete = AsyncMock(return_value=_make_resp(404))

    with patch("app.services.external_auth.httpx.AsyncClient", side_effect=lambda **kw: _client_cm(inner)):
        svc = ExternalAuthService(_ExtSettings())
        assert await svc.delete_grafana_user(7) is True


@pytest.mark.asyncio
async def test_superset_create_user_success():
    inner = MagicMock()

    async def post_side(url, **kw):
        u = str(url)
        if "security/login" in u:
            return _make_resp(200, {"access_token": "tok"})
        if "/security/users/" in u:
            return _make_resp(201, {"id": 501})
        return _make_resp(404, {})

    async def get_side(url, **kw):
        u = str(url)
        if "csrf_token" in u:
            return _make_resp(200, {"result": "csrfval"})
        if "/security/roles/" in u:
            return _make_resp(200, {"result": [{"name": "Gamma", "id": 9}]})
        return _make_resp(404, {})

    inner.post = AsyncMock(side_effect=post_side)
    inner.get = AsyncMock(side_effect=get_side)

    with patch("app.services.external_auth.httpx.AsyncClient", side_effect=lambda **kw: _client_cm(inner)):
        svc = ExternalAuthService(_ExtSettings())
        uid = await svc.create_superset_user("u@test.org", "pw", "U")
        assert uid == 501


@pytest.mark.asyncio
async def test_superset_login_fails_returns_none():
    inner = MagicMock()
    inner.post = AsyncMock(return_value=_make_resp(401, text="no"))

    with patch("app.services.external_auth.httpx.AsyncClient", side_effect=lambda **kw: _client_cm(inner)):
        svc = ExternalAuthService(_ExtSettings())
        assert await svc.create_superset_user("u@test.org", "pw", "U") is None


@pytest.mark.asyncio
async def test_superset_delete_user_success():
    inner = MagicMock()
    inner.post = AsyncMock(
        return_value=_make_resp(200, {"access_token": "t"}),
    )
    inner.delete = AsyncMock(return_value=_make_resp(204))

    with patch("app.services.external_auth.httpx.AsyncClient", side_effect=lambda **kw: _client_cm(inner)):
        svc = ExternalAuthService(_ExtSettings())
        assert await svc.delete_superset_user(3) is True
