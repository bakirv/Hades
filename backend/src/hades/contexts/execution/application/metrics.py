"""Execution Engine Prometheus metrics — one declaration site for the context.

Surfaces what an execution desk must watch: orders submitted / filled / failed
(by mode), the slippage and fees actually paid, confirmation latency and RPC
rotations. Typed accessors over the shared registry.
"""

from __future__ import annotations

from hades.shared_kernel.observability import MetricsRegistry


class ExecutionMetrics:
    """Typed accessors over the shared metrics registry for the Execution Engine."""

    def __init__(self, metrics: MetricsRegistry) -> None:
        self.submitted = metrics.counter(
            "hades_execution_orders_submitted_total",
            "Orders submitted to an executor, by mode",
            ("mode",),
        )
        self.filled = metrics.counter(
            "hades_execution_orders_filled_total",
            "Orders filled, by mode",
            ("mode",),
        )
        self.failed = metrics.counter(
            "hades_execution_orders_failed_total",
            "Orders failed, by mode and reason",
            ("mode", "reason"),
        )
        self.cancelled = metrics.counter(
            "hades_execution_orders_cancelled_total",
            "Orders cancelled before submission (e.g. slippage over budget), by reason",
            ("reason",),
        )
        self.retries = metrics.counter(
            "hades_execution_retries_total",
            "Execution retry attempts",
        )
        self.execute_seconds = metrics.histogram(
            "hades_execution_execute_seconds",
            "Wall-clock time to execute one order end-to-end",
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
        )
        self.slippage_bps = metrics.histogram(
            "hades_execution_slippage_bps",
            "Realised slippage in basis points",
            buckets=(10.0, 25.0, 50.0, 100.0, 200.0, 400.0, 800.0),
        )
        self.fees_usd = metrics.histogram(
            "hades_execution_fees_usd",
            "Fees paid per trade in USD",
            buckets=(0.001, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0),
        )
        self.confirmation_seconds = metrics.histogram(
            "hades_execution_confirmation_seconds",
            "Time to on-chain confirmation (live)",
            buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 30.0, 60.0),
        )
