"""Пресеты, схемы запросов, парсеры ресурсов, arch_to_image."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.schemas import ComputePresetLaunchRequest
from app.services.compute_presets import get_compute_preset, list_compute_presets
from app.services.k8s import (
    _deployment_uses_managed_robot_agent_image,
    arch_to_image,
    build_preset_robot_agent_deployment,
)
from app.services.resource_quantity import parse_k8s_cpu_millicores, parse_k8s_memory_bytes


def test_list_presets_includes_alpha():
    ids = {p.id for p in list_compute_presets()}
    assert "compute-peer-alpha" in ids
    assert "demo-robot-agent" in ids


def test_get_preset_unknown_returns_none():
    assert get_compute_preset("nonexistent-preset-id") is None


def test_launch_request_requires_node_or_auto():
    with pytest.raises(ValidationError):
        ComputePresetLaunchRequest(node_hostname=None, auto_orchestrate=False)


def test_launch_request_auto_without_hostname_ok():
    m = ComputePresetLaunchRequest(node_hostname=None, auto_orchestrate=True)
    assert m.auto_orchestrate is True


def test_parse_memory_plain_integer_bytes():
    assert parse_k8s_memory_bytes("2048") == 2048


def test_parse_cpu_empty_returns_zero():
    assert parse_k8s_cpu_millicores(None) == 0


def test_arch_to_image_known_arch():
    s = Settings()
    assert arch_to_image(s, "amd64") == s.compute_peer_image_amd64
    assert arch_to_image(s, "arm64") == s.compute_peer_image_arm64


def test_demo_robot_preset_is_privileged():
    preset = get_compute_preset("demo-robot-agent")
    assert preset is not None
    assert preset.privileged is True


def test_build_robot_agent_deployment_privileged_from_preset():
    preset = get_compute_preset("demo-robot-agent")
    assert preset is not None
    dep = build_preset_robot_agent_deployment(
        settings=Settings(),
        preset=preset,
        node_hostname="sber",
        image="example/robot-agent:latest",
    )
    container = dep.spec.template.spec.containers[0]
    assert container.security_context is not None
    assert container.security_context.privileged is True


def test_managed_robot_agent_image_detection():
    s = Settings()
    assert _deployment_uses_managed_robot_agent_image(s, s.control_robot_agent_image_amd64)
    assert _deployment_uses_managed_robot_agent_image(s, s.control_robot_agent_image_arm64)
    assert not _deployment_uses_managed_robot_agent_image(s, "docker.io/other:1")


def test_arch_to_image_unknown_raises():
    with pytest.raises(ValueError, match="unsupported"):
        arch_to_image(Settings(), "riscv")
