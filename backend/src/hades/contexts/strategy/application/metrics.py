"""Strategy Engine Prometheus metrics - one declaration site for the context."""

from __future__ import annotations

from hades.shared_kernel.observability import MetricsRegistry


class StrategyMetrics:
    """Typed accessors over the shared registry for the Strategy Engine."""

    def __init__(self, metrics: MetricsRegistry) -> None:
        self.signals = metrics.counter(
            "hades_strategy_signals_total",
            "Signals produced, by strategy and type",
            ("strategy", "signal_type"),
        )
        self.rejected = metrics.counter(
            "hades_strategy_signals_rejected_total",
            "Signals rejected up front by a strategy's market validation",
            ("strategy",),
        )
        self.errors = metrics.counter(
            "hades_strategy_errors_total",
            "Strategy evaluation errors (failsafe muted the strategy)",
            ("strategy",),
        )
        self.ensembles = metrics.counter(
            "hades_strategy_ensembles_total",
            "Ensemble signals produced, by decision",
            ("decision",),
        )
        self.evaluate_seconds = metrics.histogram(
            "hades_strategy_evaluate_seconds",
            "Wall-clock time to evaluate one token across all strategies",
            buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0),
        )
        self.ensemble_confidence = metrics.histogram(
            "hades_strategy_ensemble_confidence",
            "Confidence of the fused ensemble signal",
            buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
        )
