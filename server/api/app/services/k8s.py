"""Kubernetes helpers (sync client, вызывать из asyncio.to_thread)."""

from __future__ import annotations

import logging
import re
from typing import Any

from kubernetes import client, config
from kubernetes.client import (
    V1Affinity,
    V1Container,
    V1Deployment,
    V1DeploymentSpec,
    V1DeploymentStrategy,
    V1EnvVar,
    V1LabelSelector,
    V1NodeAffinity,
    V1NodeSelector,
    V1NodeSelectorRequirement,
    V1NodeSelectorTerm,
    V1ObjectMeta,
    V1PodSpec,
    V1PodTemplateSpec,
    V1ResourceRequirements,
)

from app.config import Settings

logger = logging.getLogger(__name__)

SAFE_NAME = re.compile(r"[^a-z0-9-]+")


def _configure_k8s() -> None:
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()


def _node_has_control_plane_label(labels: dict[str, str]) -> bool:
    """Стандартные метки control-plane / master (k8s, k3s)."""
    return any(
        k in labels
        for k in (
            "node-role.kubernetes.io/control-plane",
            "node-role.kubernetes.io/master",
        )
    )


def node_matches_orchestration_pool(labels: dict[str, str], settings: Settings) -> bool:
    """Нода в UI оркестрации: worker/dev из пула или optional-label; без master/control-plane."""
    if settings.k8s_hide_control_plane_nodes and _node_has_control_plane_label(labels):
        return False
    pool = settings.resource_pool_roles
    excluded = settings.orchestration_excluded_roles
    role_val = (labels.get(settings.k8s_worker_role_label) or "").strip().lower()
    if role_val in excluded:
        return False
    if role_val in pool:
        return True
    opt = settings.pool_optional_label
    if opt:
        k, v = opt
        if labels.get(k) == v:
            return True
    return False


def list_worker_nodes(settings: Settings) -> list[dict[str, Any]]:
    """Ноды пула оркестрации (worker, dev, …): master/control-plane не попадают в список."""
    _configure_k8s()
    v1 = client.CoreV1Api()
    nodes = v1.list_node()
    out: list[dict[str, Any]] = []
    for n in nodes.items:
        labels = n.metadata.labels or {}
        if not node_matches_orchestration_pool(labels, settings):
            continue
        ready = False
        for cond in n.status.conditions or []:
            if cond.type == "Ready" and cond.status == "True":
                ready = True
                break
        arch = labels.get("kubernetes.io/arch", "")
        out.append(
            {
                "name": n.metadata.name,
                "ready": ready,
                "architecture": arch,
                "labels": dict(labels),
            }
        )
    return out


def list_zenoh_deployments(settings: Settings) -> list[dict[str, Any]]:
    """Deployments в namespace zenoh."""
    _configure_k8s()
    apps = client.AppsV1Api()
    deps = apps.list_namespaced_deployment(settings.k8s_namespace)
    out: list[dict[str, Any]] = []
    for d in deps.items:
        tpl = d.spec.template.spec if d.spec.template else None
        ns_sel = dict(tpl.node_selector) if tpl and tpl.node_selector else {}
        out.append(
            {
                "name": d.metadata.name,
                "replicas": d.spec.replicas or 0,
                "readyReplicas": d.status.ready_replicas or 0,
                "nodeSelector": ns_sel,
                "labels": dict(d.metadata.labels or {}),
            }
        )
    return out


def _replicaset_to_deployment(namespace: str) -> dict[str, str]:
    """ReplicaSet.metadata.name → Deployment name (label deployment.kubernetes.io/name)."""
    apps = client.AppsV1Api()
    rss = apps.list_namespaced_replica_set(namespace)
    out: dict[str, str] = {}
    for rs in rss.items:
        if rs.metadata.name:
            dep = (rs.metadata.labels or {}).get("deployment.kubernetes.io/name")
            if dep:
                out[rs.metadata.name] = dep
    return out


def _pod_deployment_name(pod: Any, rs_to_dep: dict[str, str]) -> str | None:
    labels_dict = dict(pod.metadata.labels or {})
    dn = labels_dict.get("app.kubernetes.io/name") or labels_dict.get("app")
    if dn:
        return dn
    for ref in pod.metadata.owner_references or []:
        if ref.kind == "ReplicaSet" and ref.name:
            return rs_to_dep.get(ref.name)
    return None


def list_pods_on_nodes(settings: Settings) -> list[dict[str, Any]]:
    """Поды namespace."""
    _configure_k8s()
    v1 = client.CoreV1Api()
    ns = settings.k8s_namespace
    rs_to_dep = _replicaset_to_deployment(ns)
    pods = v1.list_namespaced_pod(ns)
    out: list[dict[str, Any]] = []
    for p in pods.items:
        labels_dict = dict(p.metadata.labels or {})
        out.append(
            {
                "name": p.metadata.name,
                "phase": p.status.phase,
                "nodeName": p.spec.node_name,
                "deploymentName": _pod_deployment_name(p, rs_to_dep),
                "labels": labels_dict,
            }
        )
    return out


def patch_deployment_node_selector(
    settings: Settings,
    deployment_name: str,
    node_hostname: str | None,
) -> None:
    """Задать nodeSelector kubernetes.io/hostname."""
    _configure_k8s()
    apps = client.AppsV1Api()
    body: dict[str, Any]
    if node_hostname:
        body = {
            "spec": {
                "template": {
                    "spec": {
                        "nodeSelector": {"kubernetes.io/hostname": node_hostname},
                    }
                }
            }
        }
    else:
        body = {"spec": {"template": {"spec": {"nodeSelector": {}}}}}
    apps.patch_namespaced_deployment(
        deployment_name,
        settings.k8s_namespace,
        body,
    )


def scale_deployment(settings: Settings, deployment_name: str, replicas: int) -> None:
    _configure_k8s()
    apps = client.AppsV1Api()
    body = {"spec": {"replicas": replicas}}
    apps.patch_namespaced_deployment(deployment_name, settings.k8s_namespace, body)


ZENOH_OVERRIDE = (
    'mode="client";connect/endpoints='
    '["tcp/zenoh-router.wolfpackcloud-zenoh.svc.cluster.local:7447"];'
    "timestamping/enabled={router:false,peer:false,client:false}"
)


def build_peer_deployment(
    *,
    settings: Settings,
    deployment_name: str,
    image: str,
    ros_domain_id: int,
    peer_shard: int,
    publish_topic: str,
    subscribe_topic: str,
    node_hostname: str | None,
    owner_id: int,
    logical_id: int,
) -> V1Deployment:
    """Deployment compute-peer."""
    labels = {
        "app.kubernetes.io/name": deployment_name,
        "app.kubernetes.io/component": "wolfpack-control-peer",
        settings.k8s_managed_by_label: settings.k8s_managed_by_value,
        "wolfpack.io/logical-node-id": str(logical_id),
        "wolfpack.io/owner-id": str(owner_id),
    }

    affinity = None
    node_selector = None
    if node_hostname:
        node_selector = {"kubernetes.io/hostname": node_hostname}
    else:
        pool_vals = sorted(settings.resource_pool_roles)
        terms = [
            V1NodeSelectorTerm(
                match_expressions=[
                    V1NodeSelectorRequirement(
                        key=settings.k8s_worker_role_label,
                        operator="In",
                        values=pool_vals,
                    )
                ]
            )
        ]
        opt = settings.pool_optional_label
        if opt:
            k, v = opt
            terms.append(
                V1NodeSelectorTerm(
                    match_expressions=[
                        V1NodeSelectorRequirement(key=k, operator="In", values=[v]),
                    ]
                )
            )
        affinity = V1Affinity(
            node_affinity=V1NodeAffinity(
                required_during_scheduling_ignored_during_execution=V1NodeSelector(
                    node_selector_terms=terms
                )
            )
        )

    container = V1Container(
        name="peer",
        image=image,
        image_pull_policy="Always",
        env=[
            V1EnvVar(name="RMW_IMPLEMENTATION", value="rmw_zenoh_cpp"),
            V1EnvVar(name="ROS_DOMAIN_ID", value=str(ros_domain_id)),
            V1EnvVar(name="ZENOH_CONFIG_OVERRIDE", value=ZENOH_OVERRIDE),
        ],
        args=[
            f"publish_topic:={publish_topic}",
            f"subscribe_topic:={subscribe_topic}",
            f"peer_shard:={peer_shard}",
        ],
        resources=V1ResourceRequirements(
            requests={"cpu": "100m", "memory": "256Mi"},
            limits={"memory": "768Mi"},
        ),
    )

    pod_spec = V1PodSpec(
        containers=[container],
        affinity=affinity,
        node_selector=node_selector,
    )

    template = V1PodTemplateSpec(
        metadata=V1ObjectMeta(labels=labels),
        spec=pod_spec,
    )

    spec = V1DeploymentSpec(
        replicas=0,
        strategy=V1DeploymentStrategy(type="Recreate"),
        selector=V1LabelSelector(match_labels={"app.kubernetes.io/name": deployment_name}),
        template=template,
    )

    meta = V1ObjectMeta(
        name=deployment_name,
        namespace=settings.k8s_namespace,
        labels=labels,
    )

    return V1Deployment(
        api_version="apps/v1",
        kind="Deployment",
        metadata=meta,
        spec=spec,
    )


def create_deployment(settings: Settings, deployment: V1Deployment) -> None:
    _configure_k8s()
    apps = client.AppsV1Api()
    apps.create_namespaced_deployment(settings.k8s_namespace, deployment)


def delete_deployment(settings: Settings, name: str) -> None:
    _configure_k8s()
    apps = client.AppsV1Api()
    apps.delete_namespaced_deployment(name, settings.k8s_namespace)


def sanitize_k8s_name(name: str, max_len: int = 40) -> str:
    s = name.strip().lower().replace("_", "-")
    s = SAFE_NAME.sub("-", s).strip("-") or "wl"
    return s[:max_len].strip("-")
