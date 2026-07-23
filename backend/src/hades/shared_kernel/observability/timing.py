"""Timing primitives — a stopwatch and rolling aggregates for latency/throughput.

These are the small, dependency-free building blocks the Performance Monitor uses
(and any context may adopt) to measure how long work takes and how fast it flows:

- :class:`Stopwatch` / :func:`measure` — time a block of work and hand the elapsed
  seconds to a sink (a histogram's ``observe``, a :class:`LatencyStat`, a log…).
- :class:`LatencyStat` — a bounded, self-contained latency summary (count, mean,
  p50, p95, max) that needs no Prometheus scrape to be read back in a snapshot.
- :class:`RollingRate` — events-per-interval over a sliding time window.

Everything is monotonic-clock based (never affected by wall-clock adjustments)
and pure-Python (the low-power VPS carries no heavyweight metrics stack).
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field


class Stopwatch:
    """A monotonic stopwatch. ``elapsed`` is valid after :meth:`stop`."""

    def __init__(self) -> None:
        self._start = time.perf_counter()
        self._elapsed: float | None = None

    def stop(self) -> float:
        self._elapsed = time.perf_counter() - self._start
        return self._elapsed

    @property
    def elapsed(self) -> float:
        return self._elapsed if self._elapsed is not None else time.perf_counter() - self._start


@contextmanager
def measure(*sinks: Callable[[float], None]) -> Iterator[Stopwatch]:
    """Time the ``with`` block; on exit push elapsed seconds to every sink.

    Sinks run even if the block raises, so a failed operation is still measured.
    """
    watch = Stopwatch()
    try:
        yield watch
    finally:
        elapsed = watch.stop()
        for sink in sinks:
            sink(elapsed)


@dataclass
class LatencyStat:
    """A bounded latency summary over the last ``capacity`` samples (seconds)."""

    capacity: int = 512
    _samples: deque[float] = field(default_factory=deque)
    count: int = 0
    total: float = 0.0
    max: float = 0.0
    last: float = 0.0

    def observe(self, seconds: float) -> None:
        self.count += 1
        self.total += seconds
        self.last = seconds
        self.max = max(self.max, seconds)
        self._samples.append(seconds)
        while len(self._samples) > self.capacity:
            self._samples.popleft()

    @property
    def mean(self) -> float:
        return self.total / self.count if self.count else 0.0

    def percentile(self, pct: float) -> float:
        if not self._samples:
            return 0.0
        ordered = sorted(self._samples)
        rank = max(0, min(len(ordered) - 1, round((pct / 100.0) * (len(ordered) - 1))))
        return ordered[rank]

    def snapshot(self) -> dict[str, float]:
        return {
            "count": float(self.count),
            "mean_ms": self.mean * 1000.0,
            "p50_ms": self.percentile(50) * 1000.0,
            "p95_ms": self.percentile(95) * 1000.0,
            "max_ms": self.max * 1000.0,
            "last_ms": self.last * 1000.0,
        }


@dataclass
class RollingRate:
    """Counts events over a sliding window and reports a per-interval rate."""

    window_seconds: float = 60.0
    _events: deque[float] = field(default_factory=deque)
    total: int = 0

    def mark(self, n: int = 1, *, now: float | None = None) -> None:
        stamp = now if now is not None else time.monotonic()
        for _ in range(n):
            self._events.append(stamp)
        self.total += n
        self._trim(stamp)

    def rate_per(self, interval_seconds: float, *, now: float | None = None) -> float:
        stamp = now if now is not None else time.monotonic()
        self._trim(stamp)
        if not self._events:
            return 0.0
        return len(self._events) * (interval_seconds / self.window_seconds)

    def _trim(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._events and self._events[0] < cutoff:
            self._events.popleft()
