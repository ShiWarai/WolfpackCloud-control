"""Роутер cluster с моком _run_k8s."""

from __future__ import annotations

import pytest


@pytest.fixture
def cluster_k8s_mock(monkeypatch):
    mib = 256
    mem_alloc = mib * 1024 * 1024 * 32
    enriched = [
        {
            "name": "w1",
            "ready": True,
            "architecture": "amd64",
            "labels": {},
            "estimated_free_memory_bytes": mem_alloc,
            "estimated_free_cpu_milli": 9000,
            "allocatable_memory_bytes": mem_alloc,
            "allocatable_cpu_milli": 10000,
            "requested_memory_bytes": 0,
            "requested_cpu_milli": 0,
            "orchestration_latency_ms": 0,
        }
    ]

    async def _run(fn, *args, **kwargs):
        name = getattr(fn, "__name__", "")
        if name == "list_worker_nodes":
            return [{"name": "w1", "ready": True, "architecture": "amd64", "labels": {"wolfpack.io/role": "worker"}}]
        if name == "list_pods_on_nodes":
            return [
                {
                    "name": "p1",
                    "phase": "Running",
                    "nodeName": "w1",
                    "deploymentName": "peer",
                    "labels": {},
                }
            ]
        if name == "list_zenoh_deployments":
            return [
                {
                    "name": "compute-peer-alpha",
                    "replicas": 1,
                    "readyReplicas": 1,
                    "nodeSelector": {},
                    "labels": {},
                }
            ]
        if name == "enrich_worker_nodes_with_scheduling_stats":
            return enriched
        if name == "launch_preset_peer":
            return None
        if name == "scale_deployment":
            return None
        raise AssertionError(f"unexpected call {name}")

    monkeypatch.setattr("app.routers.cluster._run_k8s", _run)


@pytest.fixture
def cluster_bad_arch_mock(monkeypatch):
    async def _run(fn, *args, **kwargs):
        name = getattr(fn, "__name__", "")
        if name == "list_worker_nodes":
            return [{"name": "bad", "ready": True, "architecture": "", "labels": {}}]
        if name == "launch_preset_peer":
            return None
        raise AssertionError(name)

    monkeypatch.setattr("app.routers.cluster._run_k8s", _run)


@pytest.mark.asyncio
async def test_cluster_nodes(async_client, make_access_token, cluster_k8s_mock):
    token = make_access_token(email="cn@test", sub="cns")
    r = await async_client.get("/api/cluster/nodes", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["nodes"][0]["name"] == "w1"


@pytest.mark.asyncio
async def test_cluster_orchestration_shape(async_client, make_access_token, cluster_k8s_mock):
    token = make_access_token(email="co@test", sub="cos")
    r = await async_client.get("/api/cluster/orchestration", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert "workerNodes" in body and "podsByNode" in body
    assert body["workerNodes"][0]["name"] == "w1"


@pytest.mark.asyncio
async def test_cluster_compute_presets(async_client, make_access_token, cluster_k8s_mock):
    token = make_access_token(email="cp@test", sub="cps")
    r = await async_client.get("/api/cluster/compute-presets", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    ids = {row["id"] for row in r.json()}
    assert "compute-peer-alpha" in ids


@pytest.mark.asyncio
async def test_cluster_launch_manual(async_client, make_access_token, cluster_k8s_mock):
    token = make_access_token(email="cl@test", sub="cls")
    r = await async_client.post(
        "/api/cluster/compute-presets/compute-peer-alpha/launch",
        headers={"Authorization": f"Bearer {token}"},
        json={"node_hostname": "w1", "auto_orchestrate": False},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["node_hostname"] == "w1"


@pytest.mark.asyncio
async def test_cluster_launch_auto(async_client, make_access_token, cluster_k8s_mock):
    token = make_access_token(email="ca@test", sub="cas")
    r = await async_client.post(
        "/api/cluster/compute-presets/compute-peer-alpha/launch",
        headers={"Authorization": f"Bearer {token}"},
        json={"auto_orchestrate": True},
    )
    assert r.status_code == 200
    assert r.json()["node_hostname"] == "w1"


@pytest.mark.asyncio
async def test_cluster_launch_unknown_preset(async_client, make_access_token, cluster_k8s_mock):
    token = make_access_token(email="cu@test", sub="cus")
    r = await async_client.post(
        "/api/cluster/compute-presets/no-such/launch",
        headers={"Authorization": f"Bearer {token}"},
        json={"node_hostname": "w1", "auto_orchestrate": False},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_cluster_launch_bad_arch_returns_400(async_client, make_access_token, cluster_bad_arch_mock):
    token = make_access_token(email="cb@test", sub="cbs")
    r = await async_client.post(
        "/api/cluster/compute-presets/compute-peer-alpha/launch",
        headers={"Authorization": f"Bearer {token}"},
        json={"node_hostname": "bad", "auto_orchestrate": False},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_cluster_stop_protected_zenoh(async_client, make_access_token, cluster_k8s_mock):
    token = make_access_token(email="cz@test", sub="czs")
    r = await async_client.post(
        "/api/cluster/deployments/zenoh-router/stop",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_cluster_stop_preset_allowed(async_client, make_access_token, cluster_k8s_mock):
    token = make_access_token(email="csp@test", sub="csps")
    r = await async_client.post(
        "/api/cluster/deployments/compute-peer-alpha/stop",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_cluster_stop_random_forbidden_for_user(async_client, make_access_token, cluster_k8s_mock):
    token = make_access_token(email="cr@test", sub="crs")
    r = await async_client.post(
        "/api/cluster/deployments/my-unknown-deployment/stop",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403
