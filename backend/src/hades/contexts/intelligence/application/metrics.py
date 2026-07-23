"""Wallet Intelligence Prometheus metrics — one declaration site for the context.

Everything the spec asks the knowledge base to surface: wallets registered,
clusters found, smart-money wallets seen, funding relationships, per-token
analysis latency, and the running distribution of wallet scores. Typed accessors
over the shared registry.
"""

from __future__ import annotations

from hades.shared_kernel.observability import MetricsRegistry


class IntelligenceMetrics:
    """Typed accessors over the shared metrics registry for Wallet Intelligence."""

    def __init__(self, metrics: MetricsRegistry) -> None:
        self.wallets_seen = metrics.counter(
            "hades_intel_wallets_observed_total",
            "Wallet observations processed by the intelligence engine",
        )
        self.wallets_registered = metrics.counter(
            "hades_intel_wallets_registered_total",
            "Wallets given a permanent identity for the first time",
        )
        self.clusters = metrics.counter(
            "hades_intel_clusters_detected_total",
            "Coordinated-wallet clusters detected",
        )
        self.smart_money = metrics.counter(
            "hades_intel_smart_money_detected_total",
            "Wallets classified as smart money",
        )
        self.funding_edges = metrics.counter(
            "hades_intel_funding_edges_total",
            "Funding relationships recorded, by source kind",
            ("kind",),
        )
        self.errors = metrics.counter(
            "hades_intel_errors_total",
            "Unhandled errors while building wallet intelligence",
        )
        self.analysis_seconds = metrics.histogram(
            "hades_intel_analysis_seconds",
            "Wall-clock time to build wallet intelligence for one token",
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
        )
        self.wallet_score = metrics.gauge(
            "hades_intel_wallet_score_last",
            "Most recent final wallet score",
        )
        self.registered_total = metrics.gauge(
            "hades_intel_registered_wallets",
            "Total wallets in the registry",
        )
