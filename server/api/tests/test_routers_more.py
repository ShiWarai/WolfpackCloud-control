"""Доп. роутеры: workloads list/create, metrics heartbeat, logs."""

from __future__ import annotations

import pytest

from app.models import Robot, RobotStatus, User, UserRole


@pytest.mark.asyncio
async def test_list_workloads_empty(async_client, make_access_token):
    token = make_access_token(email="lw@test", sub="lws")
    r = await async_client.get("/api/workloads", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_create_workload_k8s_error_returns_502(async_client, make_access_token, monkeypatch):
    def boom(settings, deployment):  # noqa: ARG001
        raise RuntimeError("kube unreachable")

    monkeypatch.setattr("app.routers.workloads.k8s_svc.create_deployment", boom)

    async def instant(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr("app.routers.workloads._run_k8s", instant)

    token = make_access_token(email="cw@test", sub="cws")
    r = await async_client.post(
        "/api/workloads",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "my-peer",
            "workload_type": "compute_peer",
            "architecture": "arm64",
            "publish_topic": "/a",
            "subscribe_topic": "/b",
            "peer_shard": 1,
        },
    )
    assert r.status_code == 502
    assert "kube unreachable" in r.json()["detail"]


@pytest.mark.asyncio
async def test_metrics_heartbeat_updates_last_seen(async_client, db_session):
    owner = User(email="mx@test", name="M", role=UserRole.USER, keycloak_sub="mx")
    db_session.add(owner)
    await db_session.flush()
    robot = Robot(
        name="metric-bot",
        hostname="hb",
        owner_id=owner.id,
        status=RobotStatus.ACTIVE,
        influxdb_token="heartbeat-secret-token",
    )
    db_session.add(robot)
    await db_session.commit()

    r = await async_client.post(
        "/api/metrics",
        headers={"Authorization": "Bearer heartbeat-secret-token"},
        content=b"{}",
    )
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_logs_status_disabled_influx(async_client, make_access_token):
    token = make_access_token(email="ls@test", sub="lss")
    r = await async_client.get("/api/logs/status", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["influxdb"] == "disabled"
    assert body["message"] is not None


@pytest.mark.asyncio
async def test_logs_list_requires_influx(async_client, make_access_token):
    token = make_access_token(email="lg@test", sub="lgs")
    r = await async_client.get("/api/logs", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 503
