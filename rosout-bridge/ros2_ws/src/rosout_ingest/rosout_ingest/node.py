"""Подписка на /rosout и POST в Control API."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import rclpy
from rcl_interfaces.msg import Log
from rclpy.node import Node


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

        qos = rclpy.qos.QoSProfile(depth=50)
        self.create_subscription(Log, "/rosout", self._cb, qos)

        if not self._token:
            self.get_logger().warn("ROSOUT_INGEST_TOKEN is empty — ingest будет отклонён API")

        self.get_logger().info(f"Ingest URL={self._api_url} network_id={self._network_id}")

    def _cb(self, msg: Log) -> None:
        body = {
            "network_id": self._network_id,
            "ros_node_name": msg.name,
            "level": str(msg.level),
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
            self.get_logger().warning(f"ingest HTTP {e.code}: {e.reason}")
        except Exception as e:
            self.get_logger().warning(f"ingest failed: {e}")


def main() -> None:
    rclpy.init()
    node = RosoutIngestNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
