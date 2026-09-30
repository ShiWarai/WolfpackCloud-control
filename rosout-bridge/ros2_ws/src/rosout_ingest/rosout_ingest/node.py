"""Подписка на /rosout и запись в InfluxDB (с fallback на Control API)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import rclpy
from rcl_interfaces.msg import Log
from rclpy.node import Node

from rosout_ingest.influx_writer import InfluxLogWriter, level_name


class RosoutIngestNode(Node):
    def __init__(self) -> None:
        super().__init__("rosout_ingest_node")
        self._api_url = os.environ.get(
            "CONTROL_API_INGEST_URL",
            "http://control-api.wolfpackcloud-control.svc.cluster.local:8000/api/internal/rosout/one",
        ).rstrip("/")
        self._token = os.environ.get("ROSOUT_INGEST_TOKEN", "")
        net_raw = os.environ.get("ROS_LOG_NETWORK_ID", "").strip()
        self._network_id: int | None = int(net_raw) if net_raw.isdigit() else None

        self._influx = InfluxLogWriter(
            log_fn=lambda msg: self.get_logger().info(msg),
            warn_fn=lambda msg: self.get_logger().warning(msg),
        )
        self._use_api_fallback = os.environ.get("ROSOUT_API_FALLBACK", "false").lower() in (
            "1",
            "true",
            "yes",
        )

        qos = rclpy.qos.QoSProfile(depth=50)
        self.create_subscription(Log, "/rosout", self._cb, qos)
        self.create_timer(2.0, self._flush_influx)

        if self._influx.configured:
            self.get_logger().info(
                "InfluxDB writer enabled "
                f"(org={os.environ.get('INFLUXDB_ORG', 'wolfpackcloud_influxdb')}, "
                f"bucket={os.environ.get('INFLUXDB_BUCKET_ROS_LOGS', 'ros_logs')}, "
                f"network_id={self._network_id})"
            )
        elif self._use_api_fallback:
            if not self._token:
                self.get_logger().warn("ROSOUT_INGEST_TOKEN is empty — API ingest будет отклонён")
            self.get_logger().info(f"API fallback ingest URL={self._api_url} network_id={self._network_id}")
        else:
            self.get_logger().error(
                "InfluxDB не настроен (INFLUXDB_URL/INFLUXDB_TOKEN) и API fallback выключен — "
                "логи не записываются"
            )

    def _flush_influx(self) -> None:
        self._influx.flush()

    def _cb(self, msg: Log) -> None:
        if self._influx.configured:
            self._influx.append(
                node_name=msg.name,
                level=msg.level,
                message=msg.msg,
                topic="/rosout",
            )
            return

        if not self._use_api_fallback:
            return

        body = {
            "network_id": self._network_id,
            "ros_node_name": msg.name,
            "level": level_name(msg.level),
            "topic": "/rosout",
            "message": msg.msg[:8192],
        }
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            self._api_url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "X-Ingest-Token": self._token,
            },
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=10)
        except urllib.error.HTTPError as e:
            self.get_logger().warning(f"API ingest HTTP {e.code}: {e.reason}")
        except Exception as e:
            self.get_logger().warning(f"API ingest failed: {e}")


def main() -> None:
    rclpy.init()
    node = RosoutIngestNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node._influx.flush()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
