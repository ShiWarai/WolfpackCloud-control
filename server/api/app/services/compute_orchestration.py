"""Гибридная оркестрация: статический отсев f1 и скоринг f по RAM/CPU (формулы из ТЗ)."""

from __future__ import annotations

import logging
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


logger = logging.getLogger(__name__)


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

    def _select_node_auto(
        self,
        pool_nodes: list[dict[str, Any]],
        settings: Settings,
        preset: ComputePreset,
    ) -> str:
        logger.info(
            "оркестрация: старт preset_id=%s нод_в_пуле=%d",
            preset.id,
            len(pool_nodes),
        )
        r1: list[dict[str, Any]] = []
        for n in pool_nodes:
            ok = self._static_f1(n, settings)
            logger.info(
                "оркестрация: статический отсев f1 нода=%s готовность=%s архитектура=%s прошла=%s",
                n.get("name"),
                n.get("ready"),
                n.get("architecture"),
                ok,
            )
            if ok:
                r1.append(n)
        if not r1:
            logger.warning("оркестрация: после статического отсева нет кандидатов (R1 пусто)")
            raise ValueError(
                "Нет подходящих нод после статического отсева "
                "(Ready, архитектура amd64/arm64, образ из настроек)"
            )

        m_t = int(preset.memory_request_mib) * 1024 * 1024
        c_t = int(preset.cpu_request_millicores)
        w_ram = max(0.0, float(settings.orchestration_weight_ram))
        w_cpu = max(0.0, float(settings.orchestration_weight_cpu))
        logger.info(
            "оркестрация: задача T память_MiB=%s cpu_mCPU=%s вес_ram=%s вес_cpu=%s",
            preset.memory_request_mib,
            preset.cpu_request_millicores,
            w_ram,
            w_cpu,
        )

        scored: list[tuple[float, int, str]] = []
        for n in r1:
            m_free = int(n.get("estimated_free_memory_bytes") or 0)
            c_free = int(n.get("estimated_free_cpu_milli") or 0)
            mem_a = int(n.get("allocatable_memory_bytes") or 0)
            cpu_a = int(n.get("allocatable_cpu_milli") or 0)
            mem_r = int(n.get("requested_memory_bytes") or 0)
            cpu_r = int(n.get("requested_cpu_milli") or 0)
            q_ram = (m_free - m_t) / m_t if m_t > 0 else 0.0
            q_cpu = (c_free - c_t) / c_t if c_t > 0 else 0.0
            if q_ram < 0 or q_cpu < 0:
                logger.info(
                    "оркестрация: нода %s отброшена барьером q_ram=%.4f q_cpu=%.4f "
                    "(свободно_оценка_MiB≈%.1f свободно_mCPU=%d alloc_MiB≈%.1f alloc_mCPU=%d "
                    "запросы_подов_MiB≈%.1f запросы_подов_mCPU=%d)",
                    n.get("name"),
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
            f_val = w_ram * q_ram + w_cpu * q_cpu
            lat = int(n.get("orchestration_latency_ms") or 0)
            name = str(n["name"])
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
            raise ValueError(
                "Нет нод с достаточным оценочным запасом RAM/CPU под требования задачи "
                "(динамический этап; учитываются allocatable − requests по всем подам в кластере)"
            )

        scored.sort(key=lambda t: (-t[0], t[1], t[2]))
        chosen = scored[0][2]
        ranking = [(name, round(f, 4), lat) for f, lat, name in scored]
        logger.info(
            "оркестрация: выбрана нода %s (максимум f; при равном f — меньше задержка, затем имя) рейтинг=%s",
            chosen,
            ranking,
        )
        return chosen

    @staticmethod
    def _static_f1(n: dict[str, Any], settings: Settings) -> bool:
        if not n.get("ready"):
            return False
        arch = str(n.get("architecture") or "").strip().lower()
        if arch not in ("amd64", "arm64"):
            return False
        return _configured_peer_image(settings, arch) is not None
