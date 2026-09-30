"""Запись ROS-логов в InfluxDB 2.x (Line Protocol)."""

from __future__ import annotations

import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable


def _escape_tag(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(" ", "\\ ")
        .replace(",", "\\,")
        .replace("=", "\\=")
    )


def _escape_field_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


ROS_LOG_LEVELS: dict[int, str] = {
    10: "DEBUG",
    20: "INFO",
    30: "WARN",
    40: "ERROR",
    50: "FATAL",
}


def level_name(level: int) -> str:
    return ROS_LOG_LEVELS.get(level, str(level))


class InfluxLogWriter:
    """Буферизованная запись measurement ros_log в bucket ros_logs."""

    def __init__(
        self,
        *,
        log_fn: Callable[[str], None] | None = None,
        warn_fn: Callable[[str], None] | None = None,
    ) -> None:
        self._log = log_fn or (lambda _msg: None)
        self._warn = warn_fn or (lambda _msg: None)
        self._url = os.environ.get("INFLUXDB_URL", "").strip().rstrip("/")
        self._token = os.environ.get("INFLUXDB_TOKEN", "").strip()
        self._org = os.environ.get("INFLUXDB_ORG", "wolfpackcloud_influxdb").strip()
        self._bucket = os.environ.get("INFLUXDB_BUCKET_ROS_LOGS", "ros_logs").strip()
        self._network_id = self._read_network_id()
        self._host_id = self._read_host_id()
        self._buffer: list[str] = []
        self._lock = threading.Lock()
        self._last_error: str | None = None
        self._last_success_at: float | None = None

    @staticmethod
    def _read_network_id() -> int:
        raw = os.environ.get("ROS_LOG_NETWORK_ID", "").strip()
        return int(raw) if raw.isdigit() else 0

    @staticmethod
    def _read_host_id() -> int:
        raw = os.environ.get("ROS_LOG_HOST_ID", "").strip()
        return int(raw) if raw.isdigit() else 0

    @property
    def configured(self) -> bool:
        return bool(self._url and self._token)

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def last_success_at(self) -> float | None:
        return self._last_success_at

    def append(
        self,
        *,
        node_name: str,
        level: int,
        message: str,
        topic: str = "/rosout",
    ) -> None:
        if not self.configured:
            return
        ts_ns = time.time_ns()
        line = (
            f"ros_log,host_id={self._host_id},network_id={self._network_id},"
            f"node_name={_escape_tag(node_name or 'unknown')},"
            f"level={_escape_tag(level_name(level))},"
            f"topic={_escape_tag(topic)} "
            f'message="{_escape_field_string(message[:8192])}" {ts_ns}'
        )
        flush_now = False
        with self._lock:
            self._buffer.append(line)
            if len(self._buffer) >= 50:
                flush_now = True
        if flush_now:
            self.flush()

    def flush(self) -> bool:
        if not self.configured:
            return False
        with self._lock:
            if not self._buffer:
                return True
            payload = "\n".join(self._buffer)
            self._buffer.clear()
        return self._write(payload)

    def _write(self, payload: str) -> bool:
        query = urllib.parse.urlencode(
            {
                "org": self._org,
                "bucket": self._bucket,
                "precision": "ns",
            }
        )
        url = f"{self._url}/api/v2/write?{query}"
        req = urllib.request.Request(
            url,
            data=payload.encode("utf-8"),
            headers={
                "Authorization": f"Token {self._token}",
                "Content-Type": "text/plain; charset=utf-8",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status not in (200, 204):
                    raise urllib.error.HTTPError(
                        url,
                        resp.status,
                        resp.reason or "write failed",
                        resp.headers,
                        None,
                    )
            self._last_error = None
            self._last_success_at = time.time()
            return True
        except urllib.error.HTTPError as exc:
            self._last_error = f"HTTP {exc.code}: {exc.reason}"
            self._warn(f"InfluxDB write {self._last_error}")
        except Exception as exc:
            self._last_error = str(exc)
            self._warn(f"InfluxDB write failed: {exc}")
        return False
