"""Prometheus metrics registry.

Every service is *observable*: it exposes counters, histograms and gauges on a
shared registry scraped by Prometheus. Contexts declare their own metrics but
register them here so a single ``/metrics`` endpoint exposes everything.

This module deliberately owns only the plumbing. Domain-specific metric
definitions live with their context (e.g. ``contexts/scoring`` declares a
``hades_scoring_latency_seconds`` histogram) and are registered at wiring time.
"""

from __future__ import annotations

from functools import lru_cache

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)


class MetricsRegistry:
    """Thin wrapper around a Prometheus ``CollectorRegistry``.

    Provides idempotent factory helpers so the same metric can be requested by
    name from multiple call sites without raising duplicate-registration errors.
    """

    def __init__(self) -> None:
        self._registry = CollectorRegistry()
        self._counters: dict[str, Counter] = {}
        self._gauges: dict[str, Gauge] = {}
        self._histograms: dict[str, Histogram] = {}

    @property
    def registry(self) -> CollectorRegistry:
        return self._registry

    def counter(self, name: str, documentation: str, labelnames: tuple[str, ...] = ()) -> Counter:
        if name not in self._counters:
            self._counters[name] = Counter(name, documentation, labelnames, registry=self._registry)
        return self._counters[name]

    def gauge(self, name: str, documentation: str, labelnames: tuple[str, ...] = ()) -> Gauge:
        if name not in self._gauges:
            self._gauges[name] = Gauge(name, documentation, labelnames, registry=self._registry)
        return self._gauges[name]

    def histogram(
        self,
        name: str,
        documentation: str,
        labelnames: tuple[str, ...] = (),
        buckets: tuple[float, ...] | None = None,
    ) -> Histogram:
        if name not in self._histograms:
            # Pass buckets explicitly (the client uses its default when omitted)
            # rather than via **kwargs, which is untyped for the stubs.
            if buckets is not None:
                self._histograms[name] = Histogram(
                    name, documentation, labelnames, registry=self._registry, buckets=buckets
                )
            else:
                self._histograms[name] = Histogram(
                    name, documentation, labelnames, registry=self._registry
                )
        return self._histograms[name]

    def render(self) -> bytes:
        """Return the metrics exposition payload for the ``/metrics`` endpoint."""
        return generate_latest(self._registry)


@lru_cache
def get_metrics_registry() -> MetricsRegistry:
    """Process-wide metrics registry singleton."""
    return MetricsRegistry()
