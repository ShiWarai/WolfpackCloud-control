"""Оркестрация выбора ноды для compute-peer (каркас для метрик CPU/RAM)."""

from __future__ import annotations

import random
from typing import Any


class ComputeOrchestrator:
    """Выбор целевой ноды из пула worker/dev (list_worker_nodes)."""

    def select_node(
        self,
        pool_nodes: list[dict[str, Any]],
        *,
        manual_hostname: str | None = None,
        auto_orchestrate: bool = False,
        node_metrics: dict[str, Any] | None = None,
    ) -> str:
        _ = node_metrics
        if manual_hostname and str(manual_hostname).strip():
            return str(manual_hostname).strip()
        if auto_orchestrate:
            ready = [n for n in pool_nodes if n.get("ready")]
            if not ready:
                raise ValueError("Нет Ready-нод в пуле worker/dev для оркестрации")
            # Временная «формула»: случайная нода; далее — по CPU/RAM.
            return random.choice(ready)["name"]
        raise ValueError("Укажите ноду или включите автоматическую оркестрацию")
