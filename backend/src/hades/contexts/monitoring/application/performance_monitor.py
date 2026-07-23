"""Performance Monitor — how long the platform takes and how fast it flows.

Two families of metric, both exported to Prometheus *and* summarised in a
self-contained snapshot the API/dashboard can read directly:

- **Latency** of the four pipeline stages — analysis, decision, execution,
  confirmation — via ``observe_*`` methods any context can call (e.g. wrapped in
  :func:`~hades.shared_kernel.observability.measure`). Each feeds a Prometheus
  histogram and a bounded :class:`LatencyStat` (mean / p50 / p95 / max).

- **Throughput** — tokens analysed per minute, feature computations per second,
  AI predictions per minute, operations per hour — derived **entirely from events
  the platform already publishes**. The monitor subscribes to those events, so it
  measures the live system without touching a single hot path.

It only observes; it never changes behaviour.
"""

from __future__ import annotations

from typing import Any

from hades.contexts.features.domain.events import FeaturesComputed
from hades.contexts.learning.domain.events import CommitteePredictionGenerated
from hades.contexts.risk.domain.events import TradeApproved
from hades.contexts.scanner.domain.events import TokenMetadataCollected
from hades.shared_kernel.domain.events import DomainEvent
from hades.shared_kernel.events import EventBus
from hades.shared_kernel.logging import get_logger
from hades.shared_kernel.observability import LatencyStat, MetricsRegistry, RollingRate

_logger = get_logger("monitoring.performance")

# Latency-histogram buckets (seconds) tuned for sub-second→multi-second stages.
_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)

_STAGES = ("analysis", "decision", "execution", "confirmation")


class PerformanceMonitor:
    """Aggregates latency + throughput; event-driven, Prometheus-backed."""

    def __init__(self, metrics: MetricsRegistry, *, window_seconds: float = 300.0) -> None:
        self._latency: dict[str, LatencyStat] = {s: LatencyStat() for s in _STAGES}
        self._hist = {
            s: metrics.histogram(
                f"hades_perf_{s}_seconds", f"{s.title()} stage latency (seconds)", buckets=_BUCKETS
            )
            for s in _STAGES
        }
        self._tokens = RollingRate(window_seconds=window_seconds)
        self._features = RollingRate(window_seconds=window_seconds)
        self._predictions = RollingRate(window_seconds=window_seconds)
        self._operations = RollingRate(window_seconds=max(window_seconds, 3600.0))

        self._g_tokens = metrics.gauge("hades_perf_tokens_per_min", "Tokens analysed per minute")
        self._g_features = metrics.gauge(
            "hades_perf_features_per_sec", "Feature computations per second"
        )
        self._g_predictions = metrics.gauge(
            "hades_perf_predictions_per_min", "AI predictions per minute"
        )
        self._g_operations = metrics.gauge(
            "hades_perf_operations_per_hour", "Trade operations per hour"
        )

    # -- latency (adopters call these; also driven in tests) ------------------

    def observe(self, stage: str, seconds: float) -> None:
        if stage not in self._latency:
            raise ValueError(f"unknown performance stage: {stage!r}")
        self._latency[stage].observe(seconds)
        self._hist[stage].observe(seconds)

    def observe_analysis(self, seconds: float) -> None:
        self.observe("analysis", seconds)

    def observe_decision(self, seconds: float) -> None:
        self.observe("decision", seconds)

    def observe_execution(self, seconds: float) -> None:
        self.observe("execution", seconds)

    def observe_confirmation(self, seconds: float) -> None:
        self.observe("confirmation", seconds)

    # -- throughput (event-driven) --------------------------------------------

    def mark_token(self, n: int = 1) -> None:
        self._tokens.mark(n)

    def mark_features(self, n: int = 1) -> None:
        self._features.mark(n)

    def mark_prediction(self, n: int = 1) -> None:
        self._predictions.mark(n)

    def mark_operation(self, n: int = 1) -> None:
        self._operations.mark(n)

    def register(self, event_bus: EventBus) -> None:
        event_bus.subscribe(TokenMetadataCollected.__name__, self._on_token)
        event_bus.subscribe(FeaturesComputed.__name__, self._on_features)
        event_bus.subscribe(CommitteePredictionGenerated.__name__, self._on_prediction)
        event_bus.subscribe(TradeApproved.__name__, self._on_operation)

    async def _on_token(self, event: DomainEvent) -> None:
        if isinstance(event, TokenMetadataCollected):
            self.mark_token()

    async def _on_features(self, event: DomainEvent) -> None:
        if isinstance(event, FeaturesComputed):
            self.mark_features()

    async def _on_prediction(self, event: DomainEvent) -> None:
        # Shadow predictions are comparison-only; they are not production throughput.
        if isinstance(event, CommitteePredictionGenerated) and not event.prediction.shadow:
            self.mark_prediction()

    async def _on_operation(self, event: DomainEvent) -> None:
        if isinstance(event, TradeApproved):
            self.mark_operation()

    # -- snapshot -------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        tokens_per_min = self._tokens.rate_per(60.0)
        features_per_sec = self._features.rate_per(1.0)
        predictions_per_min = self._predictions.rate_per(60.0)
        operations_per_hour = self._operations.rate_per(3600.0)

        self._g_tokens.set(tokens_per_min)
        self._g_features.set(features_per_sec)
        self._g_predictions.set(predictions_per_min)
        self._g_operations.set(operations_per_hour)

        return {
            "latency": {stage: stat.snapshot() for stage, stat in self._latency.items()},
            "throughput": {
                "tokens_per_min": round(tokens_per_min, 3),
                "features_per_sec": round(features_per_sec, 3),
                "predictions_per_min": round(predictions_per_min, 3),
                "operations_per_hour": round(operations_per_hour, 3),
            },
            "totals": {
                "tokens": self._tokens.total,
                "features": self._features.total,
                "predictions": self._predictions.total,
                "operations": self._operations.total,
            },
        }
