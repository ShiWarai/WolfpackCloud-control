"""Гибридная оркестрация: статический отсев f1 и скоринг f по RAM/CPU (формулы из ТЗ)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.config import Settings
from app.services.compute_presets import ComputePreset


def _configured_peer_image(settings: Settings, arch: str) -> str | None:
    """Тот же выбор образа, что и k8s.arch_to_image, без импорта kubernetes-клиента."""
    a = (arch or "").strip().lower()
    if a == "amd64":
        raw = settings.compute_peer_image_amd64
    elif a == "arm64":
        raw = settings.compute_peer_image_arm64
    else:
        return None
    ref = (raw or "").strip()
    return ref or None


def _configured_robot_agent_image(settings: Settings, arch: str) -> str | None:
    a = (arch or "").strip().lower()
    if a == "amd64":
        raw = settings.control_robot_agent_image_amd64
    elif a == "arm64":
        raw = settings.control_robot_agent_image_arm64
    else:
        return None
    ref = (raw or "").strip()
    return ref or None


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OrchestrationStepInfo:
    id: str
    name: str
    formula: str


ORCHESTRATION_STEPS: tuple[OrchestrationStepInfo, ...] = (
    OrchestrationStepInfo(
        id="f1",
        name="Статический отсев f1",
        formula="Ready ∧ arch∈{amd64,arm64} ∧ образ настроен ∧ role∉auto-exclude",
    ),
    OrchestrationStepInfo(
        id="q",
        name="Запас ресурсов q",
        formula="q_ram=(m_free−m_t)/m_t, q_cpu=(c_free−c_t)/c_t",
    ),
    OrchestrationStepInfo(
        id="barrier",
        name="Динамический барьер",
        formula="q_ram≥0 ∧ q_cpu≥0",
    ),
    OrchestrationStepInfo(
        id="f",
        name="Скоринг f",
        formula="f=w_ram·q_ram+w_cpu·q_cpu; argmax f → latency → имя",
    ),
)


@dataclass
class OrchestrationNodeResult:
    name: str
    ready: bool
    architecture: str
    f1_passed: bool
    f1_reason: str | None = None
    q_ram: float | None = None
    q_cpu: float | None = None
    barrier_passed: bool | None = None
    f: float | None = None
    latency_ms: int | None = None
    selected: bool = False


@dataclass
class OrchestrationTaskInfo:
    memory_request_mib: int
    cpu_request_millicores: int
    weight_ram: float
    weight_cpu: float


@dataclass
class OrchestrationTrace:
    steps: list[OrchestrationStepInfo] = field(default_factory=list)
    nodes: list[OrchestrationNodeResult] = field(default_factory=list)
    chosen: str | None = None
    ranking: list[tuple[str, float, int]] = field(default_factory=list)
    task: OrchestrationTaskInfo | None = None
    error: str | None = None


def node_excluded_from_auto_orchestration(n: dict[str, Any], settings: Settings) -> bool:
    excluded = settings.auto_orchestration_excluded_roles
    if not excluded:
        return False
    labels = n.get("labels") or {}
    role = (labels.get(settings.k8s_worker_role_label) or "").strip().lower()
    return role in excluded


class ComputeOrchestrator:
    """Выбор ноды: ручной hostname или auto (f1 × динамика, argmax f, tie-break latency → имя)."""

    def select_node(
        self,
        pool_nodes: list[dict[str, Any]],
        *,
        settings: Settings | None = None,
        preset: ComputePreset | None = None,
        manual_hostname: str | None = None,
        auto_orchestrate: bool = False,
        node_metrics: dict[str, Any] | None = None,
    ) -> str:
        _ = node_metrics
        if manual_hostname and str(manual_hostname).strip():
            return str(manual_hostname).strip()
        if auto_orchestrate:
            if settings is None or preset is None:
                raise ValueError("Внутренняя ошибка: для автооркестрации нужны settings и preset")
            return self._select_node_auto(pool_nodes, settings, preset)
        raise ValueError("Укажите ноду или включите автоматическую оркестрацию")

    def select_node_with_trace(
        self,
        pool_nodes: list[dict[str, Any]],
        *,
        settings: Settings,
        preset: ComputePreset,
    ) -> tuple[str, OrchestrationTrace]:
        trace = self._evaluate_auto(pool_nodes, settings, preset)
        if trace.error:
            raise ValueError(trace.error)
        assert trace.chosen is not None
        return trace.chosen, trace

    def _select_node_auto(
        self,
        pool_nodes: list[dict[str, Any]],
        settings: Settings,
        preset: ComputePreset,
    ) -> str:
        trace = self._evaluate_auto(pool_nodes, settings, preset)
        if trace.error:
            raise ValueError(trace.error)
        assert trace.chosen is not None
        return trace.chosen

    def _evaluate_auto(
        self,
        pool_nodes: list[dict[str, Any]],
        settings: Settings,
        preset: ComputePreset,
    ) -> OrchestrationTrace:
        trace = OrchestrationTrace(steps=list(ORCHESTRATION_STEPS))
        logger.info(
            "оркестрация: старт preset_id=%s нод_в_пуле=%d",
            preset.id,
            len(pool_nodes),
        )

        r1: list[dict[str, Any]] = []
        for n in pool_nodes:
            ok, reason = self._static_f1_check(n, settings, preset)
            log_extra = f" ({reason})" if not ok and reason else ""
            logger.info(
                "оркестрация: статический отсев f1 нода=%s готовность=%s архитектура=%s прошла=%s%s",
                n.get("name"),
                n.get("ready"),
                n.get("architecture"),
                ok,
                log_extra,
            )
            node_result = OrchestrationNodeResult(
                name=str(n.get("name") or ""),
                ready=bool(n.get("ready")),
                architecture=str(n.get("architecture") or ""),
                f1_passed=ok,
                f1_reason=reason if not ok else None,
            )
            trace.nodes.append(node_result)
            if ok:
                r1.append(n)

        m_t = int(preset.memory_request_mib) * 1024 * 1024
        c_t = int(preset.cpu_request_millicores)
        w_ram = max(0.0, float(settings.orchestration_weight_ram))
        w_cpu = max(0.0, float(settings.orchestration_weight_cpu))
        trace.task = OrchestrationTaskInfo(
            memory_request_mib=int(preset.memory_request_mib),
            cpu_request_millicores=int(preset.cpu_request_millicores),
            weight_ram=w_ram,
            weight_cpu=w_cpu,
        )
        logger.info(
            "оркестрация: задача T память_MiB=%s cpu_mCPU=%s вес_ram=%s вес_cpu=%s",
            preset.memory_request_mib,
            preset.cpu_request_millicores,
            w_ram,
            w_cpu,
        )

        if not r1:
            logger.warning("оркестрация: после статического отсева нет кандидатов (R1 пусто)")
            trace.error = (
                "Нет подходящих нод после статического отсева "
                "(Ready, архитектура amd64/arm64, образ из настроек)"
            )
            return trace

        node_results_by_name = {nr.name: nr for nr in trace.nodes}
        scored: list[tuple[float, int, str]] = []
        for n in r1:
            name = str(n["name"])
            nr = node_results_by_name[name]
            m_free = int(n.get("estimated_free_memory_bytes") or 0)
            c_free = int(n.get("estimated_free_cpu_milli") or 0)
            mem_a = int(n.get("allocatable_memory_bytes") or 0)
            cpu_a = int(n.get("allocatable_cpu_milli") or 0)
            mem_r = int(n.get("requested_memory_bytes") or 0)
            cpu_r = int(n.get("requested_cpu_milli") or 0)
            q_ram = (m_free - m_t) / m_t if m_t > 0 else 0.0
            q_cpu = (c_free - c_t) / c_t if c_t > 0 else 0.0
            nr.q_ram = round(q_ram, 4)
            nr.q_cpu = round(q_cpu, 4)
            if q_ram < 0 or q_cpu < 0:
                nr.barrier_passed = False
                logger.info(
                    "оркестрация: нода %s отброшена барьером q_ram=%.4f q_cpu=%.4f "
                    "(свободно_оценка_MiB≈%.1f свободно_mCPU=%d alloc_MiB≈%.1f alloc_mCPU=%d "
                    "запросы_подов_MiB≈%.1f запросы_подов_mCPU=%d)",
                    name,
                    q_ram,
                    q_cpu,
                    m_free / (1024 * 1024),
                    c_free,
                    mem_a / (1024 * 1024),
                    cpu_a,
                    mem_r / (1024 * 1024),
                    cpu_r,
                )
                continue
            nr.barrier_passed = True
            f_val = w_ram * q_ram + w_cpu * q_cpu
            lat = int(n.get("orchestration_latency_ms") or 0)
            nr.f = round(f_val, 4)
            nr.latency_ms = lat
            logger.info(
                "оркестрация: нода %s скоринг q_ram=%.4f q_cpu=%.4f f=%.4f "
                "задержка_ms=%s свободно_MiB≈%.1f свободно_mCPU=%d (alloc−requests)",
                name,
                q_ram,
                q_cpu,
                f_val,
                lat,
                m_free / (1024 * 1024),
                c_free,
            )
            scored.append((f_val, lat, name))

        if not scored:
            logger.warning("оркестрация: ни одна нода не прошла динамический барьер RAM/CPU")
            trace.error = (
                "Нет нод с достаточным оценочным запасом RAM/CPU под требования задачи "
                "(динамический этап; учитываются allocatable − requests по всем подам в кластере)"
            )
            return trace

        scored.sort(key=lambda t: (-t[0], t[1], t[2]))
        chosen = scored[0][2]
        ranking = [(name, round(f, 4), lat) for f, lat, name in scored]
        trace.chosen = chosen
        trace.ranking = ranking
        for nr in trace.nodes:
            nr.selected = nr.name == chosen
        logger.info(
            "оркестрация: выбрана нода %s (максимум f; при равном f — меньше задержка, затем имя) рейтинг=%s",
            chosen,
            ranking,
        )
        return trace

    @staticmethod
    def _static_f1_check(
        n: dict[str, Any],
        settings: Settings,
        preset: ComputePreset,
    ) -> tuple[bool, str | None]:
        if node_excluded_from_auto_orchestration(n, settings):
            return False, "excluded_role"
        if not n.get("ready"):
            return False, "not_ready"
        arch = str(n.get("architecture") or "").strip().lower()
        if arch not in ("amd64", "arm64"):
            return False, "bad_architecture"
        if preset.kind == "robot_agent":
            if _configured_robot_agent_image(settings, arch) is None:
                return False, "robot_agent_image_not_configured"
        elif _configured_peer_image(settings, arch) is None:
            return False, "peer_image_not_configured"
        return True, None

    @staticmethod
    def _static_f1(n: dict[str, Any], settings: Settings, preset: ComputePreset) -> bool:
        return ComputeOrchestrator._static_f1_check(n, settings, preset)[0]
