"""Управление Deployment в wolfpackcloud-zenoh."""

from __future__ import annotations

import asyncio
import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_admin, get_current_user
from app.models import Architecture, LogicalNode, Network, User, UserRole, WorkloadStatus
from app.schemas import WorkloadCreateRequest, WorkloadMigrateRequest, WorkloadResponse
from app.services import k8s as k8s_svc

router = APIRouter(prefix="/api/workloads", tags=["workloads"])
settings = get_settings()


async def _run_k8s(fn, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)


def _image_for_arch(arch: Architecture) -> str:
    if arch == Architecture.AMD64:
        return settings.compute_peer_image_amd64
    return settings.compute_peer_image_arm64


@router.get("", response_model=list[WorkloadResponse])
async def list_workloads(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[WorkloadResponse]:
    q = select(LogicalNode)
    if user.role != UserRole.ADMIN:
        q = q.where(LogicalNode.owner_id == user.id)
    result = await db.execute(q.order_by(LogicalNode.id.desc()))
    rows = result.scalars().all()
    return [WorkloadResponse.model_validate(r) for r in rows]


@router.post("", response_model=WorkloadResponse, status_code=status.HTTP_201_CREATED)
async def create_workload(
    body: WorkloadCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> WorkloadResponse:
    slug = k8s_svc.sanitize_k8s_name(body.name)
    dep_name = f"wpc-{slug}-{secrets.token_hex(3)}"

    ros_domain_id = 0
    if body.network_id is not None:
        nr = await db.execute(select(Network).where(Network.id == body.network_id))
        net = nr.scalar_one_or_none()
        if not net:
            raise HTTPException(status_code=404, detail="Сеть не найдена")
        if net.owner_id != user.id and user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Нет доступа к сети")
        ros_domain_id = net.ros_domain_id

    ln = LogicalNode(
        name=body.name,
        owner_id=user.id,
        network_id=body.network_id,
        workload_type=body.workload_type,
        k8s_deployment_name=dep_name,
        desired_node_hostname=body.node_hostname,
        status=WorkloadStatus.PENDING,
    )
    db.add(ln)
    await db.flush()

    image = _image_for_arch(body.architecture)
    dep = k8s_svc.build_peer_deployment(
        settings=settings,
        deployment_name=dep_name,
        image=image,
        ros_domain_id=ros_domain_id,
        peer_shard=body.peer_shard,
        publish_topic=body.publish_topic,
        subscribe_topic=body.subscribe_topic,
        node_hostname=body.node_hostname,
        owner_id=user.id,
        logical_id=ln.id,
    )

    try:
        await _run_k8s(k8s_svc.create_deployment, settings, dep)
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=502, detail=f"kubernetes: {e}") from e

    ln.status = WorkloadStatus.STOPPED
    await db.commit()
    await db.refresh(ln)
    return WorkloadResponse.model_validate(ln)


@router.post("/{deployment_name}/start", response_model=dict[str, Any])
async def start_workload(
    deployment_name: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    ln = await _owned_logical_node(db, user, deployment_name)
    await _run_k8s(k8s_svc.scale_deployment, settings, deployment_name, 1)
    ln.status = WorkloadStatus.RUNNING
    await db.commit()
    return {"ok": True, "deployment": deployment_name, "replicas": 1}


@router.post("/{deployment_name}/stop", response_model=dict[str, Any])
async def stop_workload(
    deployment_name: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    ln = await _owned_logical_node(db, user, deployment_name)
    await _run_k8s(k8s_svc.scale_deployment, settings, deployment_name, 0)
    ln.status = WorkloadStatus.STOPPED
    await db.commit()
    return {"ok": True, "deployment": deployment_name, "replicas": 0}


@router.post("/{deployment_name}/migrate", response_model=dict[str, Any])
async def migrate_workload(
    deployment_name: str,
    body: WorkloadMigrateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    ln = await _owned_logical_node(db, user, deployment_name)
    try:
        await _run_k8s(
            k8s_svc.patch_deployment_node_selector,
            settings,
            deployment_name,
            body.node_hostname,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    ln.desired_node_hostname = body.node_hostname
    await db.commit()
    return {"ok": True, "deployment": deployment_name, "node_hostname": body.node_hostname}


@router.delete("/{deployment_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workload(
    deployment_name: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    ln = await _owned_logical_node(db, user, deployment_name)
    try:
        await _run_k8s(k8s_svc.delete_deployment, settings, deployment_name)
    except Exception:
        pass
    await db.execute(delete(LogicalNode).where(LogicalNode.id == ln.id))
    await db.commit()


@router.post("/by-name/{deployment_name}/migrate", response_model=dict[str, Any])
async def migrate_any_deployment(
    deployment_name: str,
    body: WorkloadMigrateRequest,
    user: User = Depends(get_current_admin),
) -> dict[str, Any]:
    """Миграция любого Deployment в namespace (только admin)."""
    try:
        await _run_k8s(
            k8s_svc.patch_deployment_node_selector,
            settings,
            deployment_name,
            body.node_hostname,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return {"ok": True, "deployment": deployment_name, "node_hostname": body.node_hostname}


async def _owned_logical_node(
    db: AsyncSession,
    user: User,
    deployment_name: str,
) -> LogicalNode:
    result = await db.execute(
        select(LogicalNode).where(LogicalNode.k8s_deployment_name == deployment_name)
    )
    ln = result.scalar_one_or_none()
    if not ln:
        raise HTTPException(status_code=404, detail="Workload не найден в БД")
    if ln.owner_id != user.id and user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Нет доступа")
    return ln
