"""Кластер k8s: ноды пула ресурсов (worker/dev), деплойменты, сводка для UI оркестрации."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends

from app.config import get_settings
from app.deps import get_current_user
from app.models import User
from app.services import k8s as k8s_svc

router = APIRouter(prefix="/api/cluster", tags=["cluster"])
settings = get_settings()


async def _run_k8s(fn, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)


@router.get("/nodes", summary="Ноды пула ресурсов (worker, dev, …)")
async def cluster_nodes(_user: User = Depends(get_current_user)) -> dict[str, Any]:
    nodes = await _run_k8s(k8s_svc.list_worker_nodes, settings)
    return {"nodes": nodes}


@router.get("/deployments", summary="Deployments в wolfpackcloud-zenoh")
async def cluster_deployments(_user: User = Depends(get_current_user)) -> dict[str, Any]:
    deps = await _run_k8s(k8s_svc.list_zenoh_deployments, settings)
    return {"deployments": deps}


@router.get("/pods", summary="Поды в wolfpackcloud-zenoh")
async def cluster_pods(_user: User = Depends(get_current_user)) -> dict[str, Any]:
    pods = await _run_k8s(k8s_svc.list_pods_on_nodes, settings)
    return {"pods": pods}


@router.get("/orchestration", summary="Ноды и поды для drag-and-drop UI")
async def cluster_orchestration(_user: User = Depends(get_current_user)) -> dict[str, Any]:
    nodes = await _run_k8s(k8s_svc.list_worker_nodes, settings)
    pods = await _run_k8s(k8s_svc.list_pods_on_nodes, settings)
    deps = await _run_k8s(k8s_svc.list_zenoh_deployments, settings)
    worker_names = {n["name"] for n in nodes}
    by_node: dict[str, list[dict[str, Any]]] = {n["name"]: [] for n in nodes}
    orphan_pods: list[dict[str, Any]] = []
    for p in pods:
        nn = p.get("nodeName")
        if nn and nn in by_node:
            by_node[nn].append(p)
        elif nn:
            orphan_pods.append(p)
        else:
            orphan_pods.append(p)
    return {
        "workerNodes": nodes,
        "podsByNode": by_node,
        "orphanPods": orphan_pods,
        "deployments": deps,
    }
