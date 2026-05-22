"""Кластер k8s: ноды пула ресурсов (worker/dev), деплойменты, сводка для UI оркестрации."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from kubernetes.client.rest import ApiException

try:
    from kubernetes.client.exceptions import UnauthorizedException
except ImportError:
    UnauthorizedException = ApiException  # type: ignore[misc,assignment]
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import (
    ComputePresetLaunchRequest,
    ComputePresetLaunchResponse,
    ComputePresetResponse,
    OrchestrationNodeTraceResponse,
    OrchestrationRankingEntryResponse,
    OrchestrationStepResponse,
    OrchestrationTaskResponse,
    OrchestrationTraceResponse,
)
from app.services import deployment_events_store
from app.services import k8s as k8s_svc
from app.services.compute_orchestration import ComputeOrchestrator, OrchestrationTrace
from app.services.compute_presets import get_compute_preset, list_compute_presets

router = APIRouter(prefix="/api/cluster", tags=["cluster"])
settings = get_settings()
_orchestrator = ComputeOrchestrator()
logger = logging.getLogger(__name__)

# Не останавливать инфраструктурные деплойменты из UI
_PROTECTED_DEPLOYMENT_NAMES = frozenset({"zenoh-router"})


async def _run_k8s(fn, *args, **kwargs):
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    except (ApiException, UnauthorizedException) as e:
        reason = getattr(e, "reason", None) or str(e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"kubernetes: {reason}",
        ) from e


async def _record_deployment_event(**kwargs: Any) -> None:
    try:
        await deployment_events_store.record_deployment_event(settings, **kwargs)
    except Exception as exc:
        logger.warning("Failed to record deployment event: %s", exc)


def _trace_to_response(trace: OrchestrationTrace) -> OrchestrationTraceResponse:
    task = None
    if trace.task is not None:
        task = OrchestrationTaskResponse(
            memory_request_mib=trace.task.memory_request_mib,
            cpu_request_millicores=trace.task.cpu_request_millicores,
            weight_ram=trace.task.weight_ram,
            weight_cpu=trace.task.weight_cpu,
        )
    return OrchestrationTraceResponse(
        steps=[
            OrchestrationStepResponse(id=s.id, name=s.name, formula=s.formula)
            for s in trace.steps
        ],
        nodes=[
            OrchestrationNodeTraceResponse(
                name=n.name,
                ready=n.ready,
                architecture=n.architecture,
                f1_passed=n.f1_passed,
                f1_reason=n.f1_reason,
                q_ram=n.q_ram,
                q_cpu=n.q_cpu,
                barrier_passed=n.barrier_passed,
                f=n.f,
                latency_ms=n.latency_ms,
                selected=n.selected,
            )
            for n in trace.nodes
        ],
        chosen=trace.chosen,
        ranking=[
            OrchestrationRankingEntryResponse(node_hostname=name, f=f_val, latency_ms=lat)
            for name, f_val, lat in trace.ranking
        ],
        task=task,
        error=trace.error,
    )


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
    user: User = Depends(get_current_user),
) -> ComputePresetLaunchResponse:
    """Запуск пресета на выбранной ноде или авторазмещение (гибридная оркестрация)."""
    preset = get_compute_preset(preset_id)
    if not preset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пресет не найден")

    nodes = await _run_k8s(k8s_svc.list_worker_nodes, settings)
    orchestration_trace: OrchestrationTraceResponse | None = None
    if body.auto_orchestrate:
        nodes = await _run_k8s(k8s_svc.enrich_worker_nodes_with_scheduling_stats, settings, nodes)
    try:
        if body.auto_orchestrate:
            chosen_host, trace = _orchestrator.select_node_with_trace(
                nodes,
                settings=settings,
                preset=preset,
            )
            orchestration_trace = _trace_to_response(trace)
        else:
            chosen_host = _orchestrator.select_node(
                nodes,
                manual_hostname=(
                    body.node_hostname.strip() if body.node_hostname else None
                ),
                auto_orchestrate=False,
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
        image = k8s_svc.arch_to_image_for_preset(settings, arch, preset)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    launch_fn = (
        k8s_svc.launch_preset_robot_agent
        if preset.kind == "robot_agent"
        else k8s_svc.launch_preset_peer
    )
    try:
        await _run_k8s(
            launch_fn,
            settings,
            preset,
            chosen_host,
            image,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"kubernetes: {e}") from e

    await _record_deployment_event(
        deployment=preset.deployment_name,
        status="success",
        from_host="",
        to_host=chosen_host,
        user_id=user.id,
        preset_id=preset.id,
    )

    return ComputePresetLaunchResponse(
        ok=True,
        preset_id=preset.id,
        deployment_name=preset.deployment_name,
        node_hostname=chosen_host,
        architecture=arch,
        image=image,
        orchestration_trace=orchestration_trace,
    )


async def _user_may_stop_deployment(
    _db: AsyncSession,
    _user: User,
    deployment_name: str,
) -> bool:
    if deployment_name in _PROTECTED_DEPLOYMENT_NAMES:
        return False
    return True


@router.post("/deployments/{deployment_name}/stop", summary="Replicas=0 для Deployment в zenoh")
async def cluster_stop_deployment(
    deployment_name: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    """Остановка пода (scale 0). Любой пользователь; исключение — защищённые деплойменты (см. zenoh-router)."""
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
        from_host = await _run_k8s(
            k8s_svc.get_deployment_node_hostname,
            settings,
            deployment_name,
        )
        await _run_k8s(k8s_svc.scale_deployment, settings, deployment_name, 0)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"kubernetes: {e}") from e
    await _record_deployment_event(
        deployment=deployment_name,
        status="stopped",
        from_host=from_host,
        to_host=None,
        user_id=user.id,
    )
    return {"ok": True, "deployment": deployment_name, "replicas": 0}
