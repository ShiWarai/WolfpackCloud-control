"""Запись и чтение ROS-логов в InfluxDB."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from app.config import Settings
from app.schemas import RosOutIngestItem
from app.services import influx as influx_svc


def _line_for_item(item: RosOutIngestItem, *, ts_ns: int | None = None) -> str:
    host_id = item.host_id if item.host_id is not None else 0
    network_id = item.network_id if item.network_id is not None else 0
    node_name = influx_svc._escape_tag(item.ros_node_name or "unknown")
    level = influx_svc._escape_tag(item.level or "")
    topic = influx_svc._escape_tag(item.topic or "/rosout")
    message = influx_svc._escape_field_string(item.message)
    if ts_ns is None:
        ts_ns = int(datetime.now(timezone.utc).timestamp() * 1_000_000_000)
    return (
        f"ros_log,host_id={host_id},network_id={network_id},"
        f"node_name={node_name},level={level},topic={topic} "
        f'message="{message}" {ts_ns}'
    )


async def write_ros_logs(settings: Settings, items: list[RosOutIngestItem]) -> None:
    if not items:
        return
    lines = "\n".join(_line_for_item(item) for item in items)
    await influx_svc.write_lines(settings, settings.influxdb_bucket_ros_logs, lines)


def _entry_id(record: dict[str, Any]) -> int:
    key = "|".join(
        [
            record.get("_time", ""),
            record.get("network_id", ""),
            record.get("node_name", ""),
            record.get("level", ""),
            record.get("_value", record.get("message", "")),
        ]
    )
    digest = hashlib.sha256(key.encode()).hexdigest()
    return int(digest[:15], 16)


def _parse_time(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


async def list_ros_logs(
    settings: Settings,
    *,
    network_id: int | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 2000))
    filters = ['r._measurement == "ros_log"', 'r._field == "message"']
    if network_id is not None:
        nid = str(network_id)
        filters.append(f'(r.network_id == "{nid}" or r.network_id == "0")')

    filter_expr = " and ".join(filters)
    flux = f"""
from(bucket: "{settings.influxdb_bucket_ros_logs}")
  |> range(start: -30d)
  |> filter(fn: (r) => {filter_expr})
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: {limit})
"""
    records = await influx_svc.query_flux(settings, flux)
    out: list[dict[str, Any]] = []
    for rec in records:
        try:
            network_raw = rec.get("network_id") or "0"
            out.append(
                {
                    "id": _entry_id(rec),
                    "network_id": int(network_raw) if network_raw != "0" else None,
                    "ros_node_name": rec.get("node_name") or None,
                    "level": rec.get("level") or None,
                    "message": rec.get("_value") or "",
                    "recorded_at": _parse_time(rec["_time"]),
                }
            )
        except (KeyError, ValueError, TypeError):
            continue
    return out
