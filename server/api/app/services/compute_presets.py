"""Загрузка каталога пресетов compute-peer из YAML."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

_PRESETS_PATH = Path(__file__).resolve().parent.parent / "data" / "compute_presets.yaml"


@dataclass(frozen=True, slots=True)
class ComputePreset:
    """Описание одного заготовленного peer-deployment."""

    id: str
    deployment_name: str
    display_name: str
    publish_topic: str
    subscribe_topic: str
    peer_shard: int


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
            )
        )
    return out


def get_compute_preset(preset_id: str) -> ComputePreset | None:
    needle = (preset_id or "").strip()
    for p in list_compute_presets():
        if p.id == needle:
            return p
    return None
