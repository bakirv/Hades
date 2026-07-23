"""The Performance Monitor measures latency, throughput and timing helpers."""

from __future__ import annotations

from hades.contexts.features.domain.events import FeaturesComputed
from hades.contexts.learning.domain.events import CommitteePredictionGenerated
from hades.contexts.monitoring.application.performance_monitor import PerformanceMonitor
from hades.contexts.risk.domain.events import TradeApproved
from hades.contexts.scanner.domain.events import TokenMetadataCollected
from hades.shared_kernel.observability import LatencyStat, MetricsRegistry, RollingRate, measure


def test_latency_stat_summary() -> None:
    stat = LatencyStat()
    for value in (0.01, 0.02, 0.03, 0.04):
        stat.observe(value)
    snap = stat.snapshot()
    assert snap["count"] == 4
    assert 9.0 <= snap["mean_ms"] <= 41.0
    assert snap["max_ms"] == 40.0


def test_rolling_rate_windowing() -> None:
    rate = RollingRate(window_seconds=10.0)
    rate.mark(now=100.0)
    rate.mark(now=100.0)
    # Two events in a 10s window → 12/min when projected to 60s.
    assert rate.rate_per(60.0, now=100.0) == 12.0
    # Long after the window, the events have aged out.
    assert rate.rate_per(60.0, now=200.0) == 0.0


def test_measure_pushes_elapsed_to_sink() -> None:
    seen: list[float] = []
    with measure(seen.append):
        pass
    assert len(seen) == 1
    assert seen[0] >= 0.0


def test_observe_latency_stages() -> None:
    monitor = PerformanceMonitor(MetricsRegistry())
    monitor.observe_analysis(0.1)
    monitor.observe_decision(0.2)
    snap = monitor.snapshot()
    assert snap["latency"]["analysis"]["count"] == 1.0
    assert snap["latency"]["decision"]["count"] == 1.0
    assert snap["latency"]["execution"]["count"] == 0.0


def test_throughput_counters() -> None:
    monitor = PerformanceMonitor(MetricsRegistry())
    monitor.mark_token(3)
    monitor.mark_prediction()
    snap = monitor.snapshot()
    assert snap["totals"]["tokens"] == 3
    assert snap["totals"]["predictions"] == 1


def test_register_subscribes_the_throughput_events() -> None:
    monitor = PerformanceMonitor(MetricsRegistry())

    subscribed: list[str] = []

    class _Bus:
        def subscribe(self, event_type: str, handler: object) -> None:
            subscribed.append(event_type)

    monitor.register(_Bus())  # type: ignore[arg-type]
    assert set(subscribed) == {
        TokenMetadataCollected.__name__,
        FeaturesComputed.__name__,
        CommitteePredictionGenerated.__name__,
        TradeApproved.__name__,
    }
