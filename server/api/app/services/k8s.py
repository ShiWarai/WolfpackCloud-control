"""Kubernetes helpers (sync client, вызывать из asyncio.to_thread)."""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Any

from kubernetes import client, config
from kubernetes.client.rest import ApiException
from kubernetes.client import (
    V1Affinity,
    V1Container,
    V1Deployment,
    V1DeploymentSpec,
    V1DeploymentStrategy,
    V1EmptyDirVolumeSource,
    V1EnvVar,
    V1EnvVarSource,
    V1LabelSelector,
    V1NodeAffinity,
    V1NodeSelector,
    V1NodeSelectorRequirement,
    V1NodeSelectorTerm,
    V1ObjectFieldSelector,
    V1ObjectMeta,
    V1PodSpec,
    V1PodTemplateSpec,
    V1ResourceRequirements,
    V1SecurityContext,
    V1Volume,
    V1VolumeMount,
)

from app.config import Settings
from app.services.compute_presets import ComputePreset
from app.services.resource_quantity import parse_k8s_cpu_millicores, parse_k8s_memory_bytes

logger = logging.getLogger(__name__)

SAFE_NAME = re.compile(r"[^a-z0-9-]+")

_k8s_configured = False


def _strip_bearer_prefix(value: str) -> str:
    v = value.strip()
    if v.lower().startswith("bearer "):
        return v.split(" ", 1)[1].strip()
    return v


def normalize_incluster_bearer_auth(cfg: client.Configuration) -> None:
    """kubernetes>=36: auth_settings() читает только api_key['BearerToken'], не authorization."""
    raw = cfg.api_key or {}
    bearer_token = raw.get("BearerToken")
    auth = raw.get("authorization", "")
    token: str | None = None
    use_bearer_prefix = False
    if isinstance(bearer_token, str) and bearer_token.strip():
        token = _strip_bearer_prefix(bearer_token)
    elif isinstance(auth, str) and auth.strip():
        token = (
            auth.split(" ", 1)[1].strip()
            if auth.lower().startswith("bearer ")
            else auth.strip()
        )
        use_bearer_prefix = True
    if token:
        cfg.api_key = {"BearerToken": token}
        # In-cluster (client 36): BearerToken is "bearer <jwt>", prefix must stay empty.
        cfg.api_key_prefix = {"BearerToken": "Bearer"} if use_bearer_prefix else {}


def _configure_k8s() -> None:
    global _k8s_configured
    if _k8s_configured:
        return
    try:
        config.load_incluster_config()
        cfg = client.Configuration.get_default_copy()
        normalize_incluster_bearer_auth(cfg)
        client.Configuration.set_default(cfg)
    except config.ConfigException:
        config.load_kube_config()
    _k8s_configured = True


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


# Суммирование requests по нодам (оценка загрузки для оркестрации)
_POD_PHASE_SKIP_FOR_REQUESTS = frozenset({"Succeeded", "Failed"})


def _container_requests_mem_cpu(container: Any) -> tuple[int, int]:
    req = container.resources.requests if container.resources else None
    if not req:
        return 0, 0
    mem = parse_k8s_memory_bytes(req.get("memory"))
    cpu = parse_k8s_cpu_millicores(req.get("cpu"))
    return mem, cpu


def _pod_total_requests(pod: Any) -> tuple[int, int]:
    mem_t = 0
    cpu_t = 0
    for c in pod.spec.containers or []:
        m, c_ = _container_requests_mem_cpu(c)
        mem_t += m
        cpu_t += c_
    for c in pod.spec.init_containers or []:
        m, c_ = _container_requests_mem_cpu(c)
        mem_t += m
        cpu_t += c_
    return mem_t, cpu_t


def aggregate_pod_requests_by_node(settings: Settings) -> dict[str, dict[str, int]]:
    """Сумма requests.memory / requests.cpu по всем namespace для каждой ноды (без Failed/Succeeded)."""
    _ = settings
    _configure_k8s()
    v1 = client.CoreV1Api()
    totals: dict[str, dict[str, int]] = defaultdict(lambda: {"memory_bytes": 0, "cpu_milli": 0})
    pods = v1.list_pod_for_all_namespaces()
    for pod in pods.items or []:
        phase = pod.status.phase if pod.status else None
        if phase in _POD_PHASE_SKIP_FOR_REQUESTS:
            continue
        node = pod.spec.node_name if pod.spec else None
        if not node:
            continue
        mem, cpu = _pod_total_requests(pod)
        totals[node]["memory_bytes"] += mem
        totals[node]["cpu_milli"] += cpu
    return {k: dict(v) for k, v in totals.items()}


def node_allocatable_by_name(settings: Settings) -> dict[str, tuple[int, int]]:
    """Имя ноды → (allocatable memory bytes, allocatable cpu millicores)."""
    _ = settings
    _configure_k8s()
    v1 = client.CoreV1Api()
    out: dict[str, tuple[int, int]] = {}
    for n in v1.list_node().items or []:
        name = n.metadata.name
        if not name:
            continue
        alloc = n.status.allocatable or {}
        mem_s = alloc.get("memory")
        cpu_s = alloc.get("cpu")
        out[name] = (parse_k8s_memory_bytes(mem_s), parse_k8s_cpu_millicores(cpu_s))
    return out


def enrich_worker_nodes_with_scheduling_stats(
    settings: Settings,
    nodes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Доп. поля для гибридной оркестрации: allocatable, сумма requests, оценка free, latency для tie-break."""
    by_node_req = aggregate_pod_requests_by_node(settings)
    alloc_map = node_allocatable_by_name(settings)
    latency_key = (settings.k8s_orchestration_latency_label or "").strip()
    out: list[dict[str, Any]] = []
    for n in nodes:
        name = n["name"]
        mem_a, cpu_a = alloc_map.get(name, (0, 0))
        req = by_node_req.get(name, {"memory_bytes": 0, "cpu_milli": 0})
        mem_r = int(req["memory_bytes"])
        cpu_r = int(req["cpu_milli"])
        labels = dict(n.get("labels") or {})
        latency_ms = 0
        if latency_key:
            raw = labels.get(latency_key)
            if raw is not None:
                try:
                    latency_ms = int(str(raw).strip())
                except ValueError:
                    latency_ms = 0
        row = dict(n)
        row["allocatable_memory_bytes"] = mem_a
        row["allocatable_cpu_milli"] = cpu_a
        row["requested_memory_bytes"] = mem_r
        row["requested_cpu_milli"] = cpu_r
        row["estimated_free_memory_bytes"] = max(0, mem_a - mem_r)
        row["estimated_free_cpu_milli"] = max(0, cpu_a - cpu_r)
        row["orchestration_latency_ms"] = latency_ms
        out.append(row)
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


def node_architecture_by_hostname(settings: Settings, hostname: str) -> str:
    """kubernetes.io/arch для ноды по имени (любая нода кластера)."""
    _configure_k8s()
    v1 = client.CoreV1Api()
    hn = (hostname or "").strip()
    if not hn:
        return ""
    for n in v1.list_node().items or []:
        if n.metadata.name == hn:
            return str((n.metadata.labels or {}).get("kubernetes.io/arch", "") or "")
    raise ValueError(f"узел {hostname!r} не найден")


def _deployment_uses_managed_peer_image(settings: Settings, image: str | None) -> bool:
    """Образ контейнера peer из настроек Control (amd64/arm64 swap при смене ноды)."""
    i = (image or "").strip()
    if not i:
        return False
    return i in {
        settings.compute_peer_image_amd64.strip(),
        settings.compute_peer_image_arm64.strip(),
    }


def _deployment_uses_managed_robot_agent_image(settings: Settings, image: str | None) -> bool:
    """Образ robot-agent из настроек Control (amd64/arm64 swap при смене ноды)."""
    i = (image or "").strip()
    if not i:
        return False
    return i in {
        settings.control_robot_agent_image_amd64.strip(),
        settings.control_robot_agent_image_arm64.strip(),
    }


def patch_deployment_node_selector(
    settings: Settings,
    deployment_name: str,
    node_hostname: str | None,
) -> None:
    """Задать nodeSelector kubernetes.io/hostname; для peer/robot-agent с образами Control — подобрать image под архитектуру ноды."""
    _configure_k8s()
    apps = client.AppsV1Api()
    if not node_hostname:
        body: dict[str, Any] = {"spec": {"template": {"spec": {"nodeSelector": {}}}}}
        apps.patch_namespaced_deployment(
            deployment_name,
            settings.k8s_namespace,
            body,
        )
        return

    arch = node_architecture_by_hostname(settings, node_hostname)

    node_selector: dict[str, str] = {"kubernetes.io/hostname": node_hostname}
    if arch:
        node_selector["kubernetes.io/arch"] = arch

    patch_ops: list[dict[str, Any]] = [
        {"op": "replace", "path": "/spec/template/spec/nodeSelector", "value": node_selector},
    ]

    if arch:
        dep = apps.read_namespaced_deployment(deployment_name, settings.k8s_namespace)
        tpl = dep.spec.template
        if tpl and tpl.spec and tpl.spec.containers:
            for idx, c in enumerate(tpl.spec.containers):
                if c.name == "peer" and _deployment_uses_managed_peer_image(settings, c.image):
                    try:
                        new_image = arch_to_image(settings, arch)
                    except ValueError:
                        break
                    patch_ops.append(
                        {
                            "op": "replace",
                            "path": f"/spec/template/spec/containers/{idx}/image",
                            "value": new_image,
                        }
                    )
                    patch_ops.append(
                        {
                            "op": "replace",
                            "path": f"/spec/template/spec/containers/{idx}/imagePullPolicy",
                            "value": "Always",
                        }
                    )
                    break
                if c.name == "agent" and _deployment_uses_managed_robot_agent_image(
                    settings, c.image
                ):
                    try:
                        new_image = _image_ref_for_arch(
                            settings,
                            arch,
                            settings.control_robot_agent_image_amd64,
                            settings.control_robot_agent_image_arm64,
                        )
                    except ValueError:
                        break
                    patch_ops.append(
                        {
                            "op": "replace",
                            "path": f"/spec/template/spec/containers/{idx}/image",
                            "value": new_image,
                        }
                    )
                    patch_ops.append(
                        {
                            "op": "replace",
                            "path": f"/spec/template/spec/containers/{idx}/imagePullPolicy",
                            "value": "Always",
                        }
                    )
                    break

    apps.patch_namespaced_deployment(
        deployment_name,
        settings.k8s_namespace,
        patch_ops,
        _content_type="application/json-patch+json",
    )


def scale_deployment(settings: Settings, deployment_name: str, replicas: int) -> None:
    _configure_k8s()
    apps = client.AppsV1Api()
    body = {"spec": {"replicas": replicas}}
    apps.patch_namespaced_deployment(deployment_name, settings.k8s_namespace, body)


def get_deployment_node_hostname(settings: Settings, deployment_name: str) -> str | None:
    """Текущий nodeSelector kubernetes.io/hostname у Deployment (если задан)."""
    _configure_k8s()
    apps = client.AppsV1Api()
    dep = apps.read_namespaced_deployment(deployment_name, settings.k8s_namespace)
    selector = dep.spec.template.spec.node_selector or {}
    return selector.get("kubernetes.io/hostname")


def get_rosout_bridge_status(settings: Settings) -> str:
    """running | not_running | unknown — статус Deployment rosout-bridge."""
    try:
        _configure_k8s()
        apps = client.AppsV1Api()
        dep = apps.read_namespaced_deployment("rosout-bridge", settings.k8s_namespace)
    except ApiException:
        return "unknown"
    except Exception:
        return "unknown"

    replicas = dep.spec.replicas or 0
    ready = dep.status.ready_replicas or 0
    if replicas > 0 and ready > 0:
        return "running"
    return "not_running"


ZENOH_OVERRIDE = (
    'mode="client";connect/endpoints='
    '["tcp/zenoh-router.wolfpackcloud-zenoh.svc.cluster.local:7447"];'
    "timestamping/enabled={router:false,peer:false,client:false}"
)


def arch_to_image(settings: Settings, arch: str) -> str:
    """Образ compute-peer по kubernetes.io/arch ноды."""
    a = (arch or "").strip().lower()
    if a == "amd64":
        return settings.compute_peer_image_amd64
    if a == "arm64":
        return settings.compute_peer_image_arm64
    raise ValueError(f"unsupported node architecture: {arch!r}")


def _image_ref_for_arch(settings: Settings, arch: str, amd64: str, arm64: str) -> str:
    a = (arch or "").strip().lower()
    if a == "amd64":
        ref = (amd64 or "").strip()
    elif a == "arm64":
        ref = (arm64 or "").strip()
    else:
        raise ValueError(f"unsupported node architecture: {arch!r}")
    if not ref:
        raise ValueError(f"image not configured for architecture: {arch!r}")
    return ref


def arch_to_image_for_preset(settings: Settings, arch: str, preset: ComputePreset) -> str:
    """Образ пресета по архитектуре ноды (peer или robot-agent)."""
    if preset.kind == "robot_agent":
        return _image_ref_for_arch(
            settings,
            arch,
            settings.control_robot_agent_image_amd64,
            settings.control_robot_agent_image_arm64,
        )
    return arch_to_image(settings, arch)


CONTROL_API_CLUSTER_URL = (
    "http://control-api.wolfpackcloud-control.svc.cluster.local:8000"
)


def _namespaced_deployment_exists(
    apps: client.AppsV1Api,
    settings: Settings,
    name: str,
) -> bool:
    try:
        apps.read_namespaced_deployment(name, settings.k8s_namespace)
        return True
    except ApiException as e:
        if e.status == 404:
            return False
        raise


def build_preset_peer_deployment(
    *,
    settings: Settings,
    preset: ComputePreset,
    node_hostname: str,
    image: str,
) -> V1Deployment:
    """Deployment compute-peer из каталога пресетов (без logical node / owner)."""
    deployment_name = preset.deployment_name
    labels = {
        "app.kubernetes.io/name": deployment_name,
        "app.kubernetes.io/component": "wolfpackcloud-compute-instance-peer",
    }
    node_selector = {"kubernetes.io/hostname": node_hostname}
    try:
        arch = node_architecture_by_hostname(settings, node_hostname)
        if arch:
            node_selector["kubernetes.io/arch"] = arch
    except ValueError:
        pass

    container = V1Container(
        name="peer",
        image=image,
        image_pull_policy="Always",
        env=[
            V1EnvVar(name="RMW_IMPLEMENTATION", value="rmw_zenoh_cpp"),
            V1EnvVar(name="ROS_DOMAIN_ID", value="0"),
            V1EnvVar(name="ZENOH_CONFIG_OVERRIDE", value=ZENOH_OVERRIDE),
        ],
        args=[
            f"publish_topic:={preset.publish_topic}",
            f"subscribe_topic:={preset.subscribe_topic}",
            f"peer_shard:={preset.peer_shard}",
        ],
        resources=V1ResourceRequirements(
            requests={"cpu": "100m", "memory": "256Mi"},
            limits={"memory": "768Mi"},
        ),
    )

    pod_spec = V1PodSpec(
        containers=[container],
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


def launch_preset_peer(
    settings: Settings,
    preset: ComputePreset,
    node_hostname: str,
    image: str,
) -> None:
    """Создать deployment при отсутствии, затем привязать ноду, образ и scale=1."""
    _configure_k8s()
    apps = client.AppsV1Api()
    if not _namespaced_deployment_exists(apps, settings, preset.deployment_name):
        dep = build_preset_peer_deployment(
            settings=settings,
            preset=preset,
            node_hostname=node_hostname,
            image=image,
        )
        apps.create_namespaced_deployment(settings.k8s_namespace, dep)

    arch = node_architecture_by_hostname(settings, node_hostname)
    node_selector: dict[str, str] = {"kubernetes.io/hostname": node_hostname}
    if arch:
        node_selector["kubernetes.io/arch"] = arch

    patch_ops: list[dict[str, Any]] = [
        {"op": "replace", "path": "/spec/replicas", "value": 1},
        {"op": "replace", "path": "/spec/template/spec/nodeSelector", "value": node_selector},
        {
            "op": "replace",
            "path": "/spec/template/spec/containers/0/image",
            "value": image,
        },
        {
            "op": "replace",
            "path": "/spec/template/spec/containers/0/imagePullPolicy",
            "value": "Always",
        },
    ]
    apps.patch_namespaced_deployment(
        preset.deployment_name,
        settings.k8s_namespace,
        patch_ops,
        _content_type="application/json-patch+json",
    )


def build_preset_robot_agent_deployment(
    *,
    settings: Settings,
    preset: ComputePreset,
    node_hostname: str,
    image: str,
) -> V1Deployment:
    """Deployment demo-robot-agent из каталога пресетов."""
    deployment_name = preset.deployment_name
    labels = {
        "app.kubernetes.io/name": deployment_name,
        "app.kubernetes.io/component": "control-robot-agent",
    }
    mem_mib = int(preset.memory_request_mib)
    cpu_milli = int(preset.cpu_request_millicores)
    security_context = (
        V1SecurityContext(privileged=True) if preset.privileged else None
    )
    container = V1Container(
        name="agent",
        image=image,
        image_pull_policy="Always",
        security_context=security_context,
        env=[
            V1EnvVar(
                name="HOSTNAME",
                value_from=V1EnvVarSource(
                    field_ref=V1ObjectFieldSelector(field_path="metadata.name"),
                ),
            ),
            V1EnvVar(
                name="POD_IP",
                value_from=V1EnvVarSource(
                    field_ref=V1ObjectFieldSelector(field_path="status.podIP"),
                ),
            ),
            V1EnvVar(name="WPC_SERVER_URL", value=CONTROL_API_CLUSTER_URL),
            V1EnvVar(
                name="WPC_METRICS_URL",
                value=f"{CONTROL_API_CLUSTER_URL}/api/metrics",
            ),
            V1EnvVar(name="WPC_ROBOT_NAME", value=preset.robot_name),
        ],
        volume_mounts=[
            V1VolumeMount(name="agent-data", mount_path="/var/lib/wpc-agent"),
        ],
        resources=V1ResourceRequirements(
            requests={
                "cpu": f"{cpu_milli}m",
                "memory": f"{mem_mib}Mi",
            },
            limits={"memory": f"{max(mem_mib * 2, mem_mib)}Mi"},
        ),
    )
    pod_spec = V1PodSpec(
        containers=[container],
        node_selector={"kubernetes.io/hostname": node_hostname},
        volumes=[V1Volume(name="agent-data", empty_dir=V1EmptyDirVolumeSource())],
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


def launch_preset_robot_agent(
    settings: Settings,
    preset: ComputePreset,
    node_hostname: str,
    image: str,
) -> None:
    """Создать robot-agent deployment при отсутствии, затем привязать ноду, образ и scale=1."""
    _configure_k8s()
    apps = client.AppsV1Api()
    if not _namespaced_deployment_exists(apps, settings, preset.deployment_name):
        dep = build_preset_robot_agent_deployment(
            settings=settings,
            preset=preset,
            node_hostname=node_hostname,
            image=image,
        )
        apps.create_namespaced_deployment(settings.k8s_namespace, dep)

    arch = node_architecture_by_hostname(settings, node_hostname)
    node_selector: dict[str, str] = {"kubernetes.io/hostname": node_hostname}
    if arch:
        node_selector["kubernetes.io/arch"] = arch

    body: dict[str, Any] = {
        "spec": {
            "replicas": 1,
            "template": {
                "spec": {
                    "nodeSelector": node_selector,
                    "containers": [
                        {
                            "name": "agent",
                            "image": image,
                            "imagePullPolicy": "Always",
                            **(
                                {"securityContext": {"privileged": True}}
                                if preset.privileged
                                else {}
                            ),
                        }
                    ],
                }
            },
        }
    }
    apps.patch_namespaced_deployment(
        preset.deployment_name,
        settings.k8s_namespace,
        body,
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
