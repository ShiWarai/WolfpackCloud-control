"""Клиент InfluxDB 2.x (write + Flux query)."""

from __future__ import annotations

import csv
import io
import logging
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


class InfluxError(Exception):
    """InfluxDB недоступен или вернул ошибку."""


def _escape_tag(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(" ", "\\ ")
        .replace(",", "\\,")
        .replace("=", "\\=")
    )


def _escape_field_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


async def write_lines(settings: Settings, bucket: str, lines: str) -> None:
    if not settings.influxdb_configured:
        raise InfluxError("InfluxDB не настроен")
    if not lines.strip():
        return

    url = f"{settings.influxdb_url.rstrip('/')}/api/v2/write"
    params = {
        "org": settings.influxdb_org,
        "bucket": bucket,
        "precision": "ns",
    }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                url,
                params=params,
                headers={
                    "Authorization": f"Token {settings.influxdb_token}",
                    "Content-Type": "text/plain; charset=utf-8",
                },
                content=lines,
                timeout=15.0,
            )
        except httpx.RequestError as exc:
            logger.warning("InfluxDB write failed: %s", exc)
            raise InfluxError(str(exc)) from exc

    if response.status_code not in (200, 204):
        logger.warning("InfluxDB write HTTP %s: %s", response.status_code, response.text)
        raise InfluxError(f"HTTP {response.status_code}: {response.text}")


async def query_flux(settings: Settings, flux: str) -> list[dict[str, Any]]:
    if not settings.influxdb_configured:
        raise InfluxError("InfluxDB не настроен")

    url = f"{settings.influxdb_url.rstrip('/')}/api/v2/query"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                url,
                params={"org": settings.influxdb_org},
                headers={
                    "Authorization": f"Token {settings.influxdb_token}",
                    "Accept": "application/csv",
                    "Content-type": "application/vnd.flux",
                },
                content=flux,
                timeout=30.0,
            )
        except httpx.RequestError as exc:
            logger.warning("InfluxDB query failed: %s", exc)
            raise InfluxError(str(exc)) from exc

    if response.status_code != 200:
        raise InfluxError(f"HTTP {response.status_code}: {response.text}")

    return _parse_flux_csv(response.text)


def _parse_flux_csv(raw: str) -> list[dict[str, Any]]:
    """Парсит annotated CSV от InfluxDB Flux."""
    rows: list[dict[str, Any]] = []
    header: list[str] | None = None

    for line in raw.splitlines():
        if not line or line.startswith("#"):
            continue
        if header is None:
            header = next(csv.reader([line]))
            continue
        values = next(csv.reader([line]))
        if len(values) != len(header):
            continue
        record = dict(zip(header, values, strict=False))
        time_val = record.get("_time", "")
        if not time_val or time_val == "_time":
            continue
        rows.append(record)
    return rows


async def ping(settings: Settings) -> bool:
    if not settings.influxdb_configured:
        return False
    url = f"{settings.influxdb_url.rstrip('/')}/health"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=5.0)
        return response.status_code == 200
    except httpx.RequestError:
        return False
