"""Кластер k8s: ноды пула ресурсов (worker/dev), деплойменты, сводка для UI оркестрации."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user
from app.models import LogicalNode, User, UserRole
from app.schemas import (
    ComputePresetLaunchRequest,
    ComputePresetLaunchResponse,
    ComputePresetResponse,
)
from app.services import k8s as k8s_svc
from app.services.compute_orchestration import ComputeOrchestrator
from app.services.compute_presets import get_compute_preset, list_compute_presets

router = APIRouter(prefix="/api/cluster", tags=["cluster"])
settings = get_settings()
_orchestrator = ComputeOrchestrator()

# Не останавливать инфраструктурные деплойменты из UI
_PROTECTED_DEPLOYMENT_NAMES = frozenset({"zenoh-router"})


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


@router.get("/compute-presets", response_model=list[ComputePresetResponse])
async def cluster_compute_presets(
    _user: User = Depends(get_current_user),
) -> list[ComputePresetResponse]:
    """Каталог заготовленных compute-peer (alpha/beta/gamma)."""
    return [
        ComputePresetResponse(
            id=p.id,
            deployment_name=p.deployment_name,
            display_name=p.display_name,
            publish_topic=p.publish_topic,
            subscribe_topic=p.subscribe_topic,
            peer_shard=p.peer_shard,
            memory_request_mib=p.memory_request_mib,
            cpu_request_millicores=p.cpu_request_millicores,
        )
        for p in list_compute_presets()
    ]


@router.post("/compute-presets/{preset_id}/launch", response_model=ComputePresetLaunchResponse)
async def cluster_launch_compute_preset(
    preset_id: str,
    body: ComputePresetLaunchRequest,
    _user: User = Depends(get_current_user),
) -> ComputePresetLaunchResponse:
    """Запуск пресета на выбранной ноде или авторазмещение (гибридная оркестрация)."""
    preset = get_compute_preset(preset_id)
    if not preset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пресет не найден")

    nodes = await _run_k8s(k8s_svc.list_worker_nodes, settings)
    if body.auto_orchestrate:
        nodes = await _run_k8s(k8s_svc.enrich_worker_nodes_with_scheduling_stats, settings, nodes)
    try:
        chosen_host = _orchestrator.select_node(
            nodes,
            settings=settings if body.auto_orchestrate else None,
            preset=preset if body.auto_orchestrate else None,
            manual_hostname=(
                None
                if body.auto_orchestrate
                else (body.node_hostname.strip() if body.node_hostname else None)
            ),
            auto_orchestrate=body.auto_orchestrate,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    target = next((n for n in nodes if n["name"] == chosen_host), None)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нода не в пуле оркестрации",
        )
    if not target.get("ready"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нода не Ready",
        )

    arch = str(target.get("architecture") or "")
    try:
        image = k8s_svc.arch_to_image(settings, arch)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    try:
        await _run_k8s(
            k8s_svc.launch_preset_peer,
            settings,
            preset,
            chosen_host,
            image,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"kubernetes: {e}") from e

    return ComputePresetLaunchResponse(
        ok=True,
        preset_id=preset.id,
        deployment_name=preset.deployment_name,
        node_hostname=chosen_host,
        architecture=arch,
        image=image,
    )


async def _user_may_stop_deployment(
    db: AsyncSession,
    user: User,
    deployment_name: str,
) -> bool:
    if deployment_name in _PROTECTED_DEPLOYMENT_NAMES:
        return False
    preset_names = {p.deployment_name for p in list_compute_presets()}
    if deployment_name in preset_names:
        return True
    if user.role == UserRole.ADMIN:
        return True
    r = await db.execute(
        select(LogicalNode).where(LogicalNode.k8s_deployment_name == deployment_name),
    )
    ln = r.scalar_one_or_none()
    return ln is not None and ln.owner_id == user.id


@router.post("/deployments/{deployment_name}/stop", summary="Replicas=0 для Deployment в zenoh")
async def cluster_stop_deployment(
    deployment_name: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    """Остановка пода (scale 0). Пресеты — любой пользователь; иначе admin или владелец workload."""
    if deployment_name in _PROTECTED_DEPLOYMENT_NAMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Этот деплоймент нельзя останавливать из интерфейса",
        )
    if not await _user_may_stop_deployment(db, user, deployment_name):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет прав на остановку этого деплоймента",
        )
    try:
        await _run_k8s(k8s_svc.scale_deployment, settings, deployment_name, 0)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"kubernetes: {e}") from e
    return {"ok": True, "deployment": deployment_name, "replicas": 0}
