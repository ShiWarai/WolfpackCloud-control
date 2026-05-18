"""Юнит-тесты гибридной оркестрации (q, барьер, скоринг f, argmax, tie-break)."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.services.compute_orchestration import ComputeOrchestrator
from app.services.compute_presets import ComputePreset


def _preset(
    mem_mib: int = 256,
    cpu_milli: int = 100,
) -> ComputePreset:
    return ComputePreset(
        id="t",
        deployment_name="t-dep",
        display_name="T",
        publish_topic="/p",
        subscribe_topic="/s",
        peer_shard=0,
        memory_request_mib=mem_mib,
        cpu_request_millicores=cpu_milli,
    )


def _node(
    name: str,
    *,
    ready: bool = True,
    arch: str = "amd64",
    m_free: int | None = None,
    c_free: int | None = None,
    latency_ms: int = 0,
) -> dict:
    mib = 256
    milli = 100
    m = (mib * 1024 * 1024) * 2 if m_free is None else m_free
    c = milli * 2 if c_free is None else c_free
    return {
        "name": name,
        "ready": ready,
        "architecture": arch,
        "estimated_free_memory_bytes": m,
        "estimated_free_cpu_milli": c,
        "orchestration_latency_ms": latency_ms,
    }


@pytest.fixture
def settings() -> Settings:
    return Settings()


def test_static_f1_rejects_not_ready(settings: Settings) -> None:
    o = ComputeOrchestrator()
    assert o._static_f1(_node("a", ready=False), settings) is False


def test_static_f1_rejects_bad_arch(settings: Settings) -> None:
    o = ComputeOrchestrator()
    assert o._static_f1(_node("a", arch="riscv64"), settings) is False


def test_static_f1_accepts_amd64(settings: Settings) -> None:
    o = ComputeOrchestrator()
    assert o._static_f1(_node("a", arch="amd64"), settings) is True


def test_static_f1_rejects_missing_peer_image_ref() -> None:
    o = ComputeOrchestrator()
    s = Settings(compute_peer_image_amd64="   ", compute_peer_image_arm64="")
    assert o._static_f1(_node("a", arch="amd64"), s) is False


def test_auto_skips_under_barrier_ram(settings: Settings) -> None:
    o = ComputeOrchestrator()
    mib = 256
    m_t = mib * 1024 * 1024
    # Ровно на грани по CPU, не хватает RAM
    nodes = [
        _node(
            "bad",
            m_free=m_t - 1,
            c_free=500,
        ),
        _node(
            "good",
            m_free=m_t * 3,
            c_free=500,
        ),
    ]
    picked = o._select_node_auto(nodes, settings, _preset())
    assert picked == "good"


def test_auto_argmax_higher_spare_wins(settings: Settings) -> None:
    o = ComputeOrchestrator()
    mib = 256
    milli = 100
    m_t = mib * 1024 * 1024
    # q_ram=1, q_cpu=1 для low; q_ram=3, q_cpu=1 для high → f выше у high при w=1
    low_m = m_t + m_t
    high_m = m_t + 3 * m_t
    nodes = [
        _node("low-node", m_free=low_m, c_free=milli * 2),
        _node("high-node", m_free=high_m, c_free=milli * 2),
    ]
    picked = o._select_node_auto(nodes, settings, _preset())
    assert picked == "high-node"


def test_auto_tie_break_latency_then_name(settings: Settings) -> None:
    o = ComputeOrchestrator()
    # Две ноды с одинаковым spare → одинаковый f; меньшая latency, затем имя
    nodes = [
        _node("zebra", latency_ms=5),
        _node("alpha", latency_ms=10),
        _node("beta", latency_ms=5),
    ]
    picked = o._select_node_auto(nodes, settings, _preset())
    assert picked == "beta"

    nodes2 = [
        _node("m1", latency_ms=3),
        _node("m2", latency_ms=3),
    ]
    assert o._select_node_auto(nodes2, settings, _preset()) == "m1"


def test_auto_no_r1_raises(settings: Settings) -> None:
    o = ComputeOrchestrator()
    nodes = [_node("x", arch="riscv64")]
    with pytest.raises(ValueError, match="статического отсева"):
        o._select_node_auto(nodes, settings, _preset())


def test_auto_all_below_barrier_raises(settings: Settings) -> None:
    o = ComputeOrchestrator()
    mib = 256
    m_t = mib * 1024 * 1024
    nodes = [
        _node("a", m_free=m_t // 2, c_free=1000),
        _node("b", m_free=m_t, c_free=10),
    ]
    with pytest.raises(ValueError, match="достаточным оценочным запасом"):
        o._select_node_auto(nodes, settings, _preset())
