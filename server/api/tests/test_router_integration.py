"""Интеграционные тесты роутеров через ASGI (httpx AsyncClient)."""

from __future__ import annotations

import pytest

from app.models import LogicalNode, User, UserRole, WorkloadStatus


@pytest.mark.asyncio
async def test_health(async_client):
    r = await async_client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


@pytest.mark.asyncio
async def test_auth_me_returns_profile(async_client, make_access_token):
    token = make_access_token()
    r = await async_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == "user@example.com"
    assert data["role"] == "user"


@pytest.mark.asyncio
async def test_auth_me_requires_bearer(async_client):
    r = await async_client.get("/api/auth/me")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_admin_migrate_by_name(async_client, make_access_token, monkeypatch):
    calls: list[tuple[str, str | None]] = []

    def fake_patch(settings, deployment_name, node_hostname):  # noqa: ARG001
        calls.append((deployment_name, node_hostname))

    monkeypatch.setattr(
        "app.routers.workloads.k8s_svc.patch_deployment_node_selector",
        fake_patch,
    )

    async def instant(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr("app.routers.workloads._run_k8s", instant)

    token = make_access_token(
        sub="admin-sub",
        email="admin@test.local",
        preferred_username="adminuser",
        realm_roles=["admin"],
    )
    r = await async_client.post(
        "/api/workloads/by-name/preset-peer/migrate",
        json={"node_hostname": "target-host"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert calls == [("preset-peer", "target-host")]


@pytest.mark.asyncio
async def test_user_migrate_calls_patch(async_client, make_access_token, db_session, monkeypatch):
    user = User(
        email="own@test.local",
        keycloak_sub="sub-own",
        name="Owner",
        role=UserRole.USER,
    )
    db_session.add(user)
    await db_session.flush()

    ln = LogicalNode(
        name="wl",
        owner_id=user.id,
        workload_type="peer",
        k8s_deployment_name="dep-owned-migrate",
        status=WorkloadStatus.STOPPED,
    )
    db_session.add(ln)
    await db_session.commit()

    calls: list[tuple[str, str | None]] = []

    def fake_patch(settings, deployment_name, node_hostname):  # noqa: ARG001
        calls.append((deployment_name, node_hostname))

    monkeypatch.setattr(
        "app.routers.workloads.k8s_svc.patch_deployment_node_selector",
        fake_patch,
    )

    async def instant(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr("app.routers.workloads._run_k8s", instant)

    token = make_access_token(sub="sub-own", email="own@test.local", preferred_username="own")
    r = await async_client.post(
        "/api/workloads/dep-owned-migrate/migrate",
        json={"node_hostname": "node-b"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert calls == [("dep-owned-migrate", "node-b")]


@pytest.mark.asyncio
async def test_migrate_value_error_maps_to_400(async_client, make_access_token, monkeypatch):
    def boom(settings, deployment_name, node_hostname):  # noqa: ARG001
        raise ValueError("узел 'ghost' не найден")

    monkeypatch.setattr(
        "app.routers.workloads.k8s_svc.patch_deployment_node_selector",
        boom,
    )

    async def instant(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr("app.routers.workloads._run_k8s", instant)

    token = make_access_token(
        sub="adm2",
        email="admin2@test.local",
        realm_roles=["admin"],
    )
    r = await async_client.post(
        "/api/workloads/by-name/x/migrate",
        json={"node_hostname": "ghost"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
