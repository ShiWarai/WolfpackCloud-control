"""Запись и чтение событий деплоя в InfluxDB."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from app.config import Settings
from app.services import influx as influx_svc


def _escape_opt_tag(value: str | None) -> str:
    if not value:
        return "none"
    return influx_svc._escape_tag(value)


async def record_deployment_event(
    settings: Settings,
    *,
    deployment: str,
    status: str,
    from_host: str | None = None,
    to_host: str | None = None,
    user_id: int | None = None,
    preset_id: str | None = None,
) -> None:
    if not settings.influxdb_configured:
        return

    dep = influx_svc._escape_tag(deployment)
    st = influx_svc._escape_tag(status)
    fh = _escape_opt_tag(from_host)
    th = _escape_opt_tag(to_host)
    uid = user_id if user_id is not None else 0
    preset = influx_svc._escape_tag(preset_id or "")
    ts_ns = int(datetime.now(timezone.utc).timestamp() * 1_000_000_000)
    line = (
        f"deployment_event,deployment={dep},from_host={fh},to_host={th},status={st},"
        f"preset_id={preset} user_id={uid}i {ts_ns}"
    )
    await influx_svc.write_lines(settings, settings.influxdb_bucket_deployment_events, line)


def _event_id(record: dict[str, Any]) -> int:
    key = "|".join(
        [
            record.get("_time", ""),
            record.get("deployment", ""),
            record.get("status", ""),
            record.get("from_host", ""),
            record.get("to_host", ""),
        ]
    )
    return int(hashlib.sha256(key.encode()).hexdigest()[:15], 16)


def _parse_time(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _none_if_empty(value: str | None) -> str | None:
    if value is None or value == "" or value == "none":
        return None
    return value


async def list_deployment_events(
    settings: Settings,
    *,
    deployment: str | None = None,
    status: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 2000))
    filters = ['r._measurement == "deployment_event"']
    if deployment:
        dep = influx_svc._escape_tag(deployment)
        filters.append(f'r.deployment == "{dep}"')
    if status:
        st = influx_svc._escape_tag(status)
        filters.append(f'r.status == "{st}"')

    filter_expr = " and ".join(filters)
    flux = f"""
from(bucket: "{settings.influxdb_bucket_deployment_events}")
  |> range(start: -90d)
  |> filter(fn: (r) => {filter_expr})
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: {limit})
"""
    records = await influx_svc.query_flux(settings, flux)
    out: list[dict[str, Any]] = []
    for rec in records:
        try:
            out.append(
                {
                    "id": _event_id(rec),
                    "deployment": rec.get("deployment") or "",
                    "from_host": _none_if_empty(rec.get("from_host")),
                    "to_host": _none_if_empty(rec.get("to_host")),
                    "status": rec.get("status") or "",
                    "user_id": int(rec["user_id"]) if rec.get("user_id") else None,
                    "preset_id": _none_if_empty(rec.get("preset_id")),
                    "created_at": _parse_time(rec["_time"]),
                    "started_at": None,
                    "finished_at": None,
                }
            )
        except (KeyError, ValueError, TypeError):
            continue
    return out
