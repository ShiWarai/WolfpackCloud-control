"""Парсинг Kubernetes quantity для оркестрации."""

from app.services.resource_quantity import parse_k8s_cpu_millicores, parse_k8s_memory_bytes


def test_parse_memory_mebibytes_suffixes() -> None:
    assert parse_k8s_memory_bytes("256Mi") == 256 * 1024 * 1024
    assert parse_k8s_memory_bytes("1Ki") == 1024
    assert parse_k8s_memory_bytes("0") == 0
    assert parse_k8s_memory_bytes(None) == 0
    assert parse_k8s_memory_bytes("   ") == 0


def test_parse_cpu_millicores() -> None:
    assert parse_k8s_cpu_millicores("100m") == 100
    assert parse_k8s_cpu_millicores("1") == 1000
    assert parse_k8s_cpu_millicores("2.5") == 2500
