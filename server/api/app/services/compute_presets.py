"""Загрузка каталога пресетов compute-peer из YAML."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

_PRESETS_PATH = Path(__file__).resolve().parent.parent / "data" / "compute_presets.yaml"


_DEFAULT_MEMORY_MIB = 256
_DEFAULT_CPU_MILLI = 100


@dataclass(frozen=True, slots=True)
class ComputePreset:
    """Описание одного заготовленного peer-deployment."""

    id: str
    deployment_name: str
    display_name: str
    publish_topic: str
    subscribe_topic: str
    peer_shard: int
    #: Запрос памяти задачи T (MiB), как в Deployment requests.memory
    memory_request_mib: int
    #: Запрос CPU задачи T (millicores), как в Deployment requests.cpu (100m → 100)
    cpu_request_millicores: int


def _load_raw() -> dict:
    with _PRESETS_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def list_compute_presets() -> list[ComputePreset]:
    data = _load_raw()
    items = data.get("presets") or []
    out: list[ComputePreset] = []
    for row in items:
        out.append(
            ComputePreset(
                id=str(row["id"]),
                deployment_name=str(row["deployment_name"]),
                display_name=str(row.get("display_name") or row["id"]),
                publish_topic=str(row["publish_topic"]),
                subscribe_topic=str(row["subscribe_topic"]),
                peer_shard=int(row["peer_shard"]),
                memory_request_mib=int(row.get("memory_request_mib", _DEFAULT_MEMORY_MIB)),
                cpu_request_millicores=int(
                    row.get("cpu_request_millicores", _DEFAULT_CPU_MILLI),
                ),
            )
        )
    return out


def get_compute_preset(preset_id: str) -> ComputePreset | None:
    needle = (preset_id or "").strip()
    for p in list_compute_presets():
        if p.id == needle:
            return p
    return None
