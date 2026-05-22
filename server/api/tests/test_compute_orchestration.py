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
        kind="peer",
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
    labels: dict | None = None,
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
        "labels": labels or {},
    }


@pytest.fixture
def settings() -> Settings:
    return Settings()


def test_static_f1_rejects_not_ready(settings: Settings) -> None:
    o = ComputeOrchestrator()
    p = _preset()
    assert o._static_f1(_node("a", ready=False), settings, p) is False


def test_static_f1_rejects_bad_arch(settings: Settings) -> None:
    o = ComputeOrchestrator()
    p = _preset()
    assert o._static_f1(_node("a", arch="riscv64"), settings, p) is False


def test_static_f1_accepts_amd64(settings: Settings) -> None:
    o = ComputeOrchestrator()
    p = _preset()
    assert o._static_f1(_node("a", arch="amd64"), settings, p) is True


def test_static_f1_rejects_missing_peer_image_ref() -> None:
    o = ComputeOrchestrator()
    s = Settings(compute_peer_image_amd64="   ", compute_peer_image_arm64="")
    p = _preset()
    assert o._static_f1(_node("a", arch="amd64"), s, p) is False


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


def test_select_node_manual_hostname_trims() -> None:
    orch = ComputeOrchestrator()
    assert orch.select_node([{}], manual_hostname="  node-z  ") == "node-z"


def test_select_node_auto_requires_settings_and_preset(settings: Settings) -> None:
    orch = ComputeOrchestrator()
    preset = _preset()
    with pytest.raises(ValueError, match="settings"):
        orch.select_node([_node("a")], auto_orchestrate=True, preset=preset)
    with pytest.raises(ValueError, match="preset"):
        orch.select_node([_node("a")], auto_orchestrate=True, settings=settings)


def test_select_node_requires_explicit_mode() -> None:
    orch = ComputeOrchestrator()
    with pytest.raises(ValueError, match="ноду"):
        orch.select_node([_node("a")])


def test_static_f1_rejects_auto_orchestration_blocked(settings: Settings) -> None:
    o = ComputeOrchestrator()
    node = _node(
        "sber",
        labels={"wolfpack.io/auto-orchestration": "blocked"},
    )
    ok, reason = o._static_f1_check(node, settings, _preset())
    assert ok is False
    assert reason == "auto_orchestration_blocked"


def test_auto_skips_blocked_node(settings: Settings) -> None:
    o = ComputeOrchestrator()
    nodes = [
        _node("sber", labels={"wolfpack.io/auto-orchestration": "blocked"}),
        _node("good"),
    ]
    picked = o._select_node_auto(nodes, settings, _preset())
    assert picked == "good"


def test_manual_launch_on_blocked_node_allowed(settings: Settings) -> None:
    orch = ComputeOrchestrator()
    node = _node("sber", labels={"wolfpack.io/auto-orchestration": "blocked"})
    assert orch.select_node([node], manual_hostname="sber") == "sber"


def test_evaluate_auto_trace_shape(settings: Settings) -> None:
    o = ComputeOrchestrator()
    trace = o._evaluate_auto([_node("alpha"), _node("beta")], settings, _preset())
    assert trace.error is None
    assert trace.chosen in ("alpha", "beta")
    assert len(trace.steps) == 4
    assert {s.id for s in trace.steps} == {"f1", "q", "barrier", "f"}
    assert len(trace.nodes) == 2
    assert trace.task is not None
    assert trace.ranking
    selected = [n for n in trace.nodes if n.selected]
    assert len(selected) == 1
    assert selected[0].name == trace.chosen


def test_evaluate_auto_trace_blocked_reason(settings: Settings) -> None:
    o = ComputeOrchestrator()
    trace = o._evaluate_auto(
        [_node("sber", labels={"wolfpack.io/auto-orchestration": "blocked"})],
        settings,
        _preset(),
    )
    assert trace.error is not None
    assert trace.nodes[0].f1_reason == "auto_orchestration_blocked"
