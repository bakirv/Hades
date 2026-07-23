"""In-memory stores for the strategy signal trail and self-evaluation.

The strategy runtime keeps its authoritative state in memory (like the Execution
Engine's order ledger and the Portfolio book) and publishes snapshots to Redis for
the dashboard. These satisfy the :class:`SignalStore` and :class:`PerformanceStore`
ports; a Postgres binding can replace either without touching the engine, which
depends only on the ports.

The performance store keeps each strategy's raw outcomes and recomputes its
scorecard on read with the pure :class:`SelfEvaluator` - so a strategy's Sharpe /
Profit Factor / expectancy always reflect its complete realised history.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from hades.contexts.strategy.application.evaluation import SelfEvaluator
from hades.contexts.strategy.domain.models import StrategyOutcome, StrategyPerformance


class InMemorySignalStore:
    """Bounded rings of per-strategy signals and fused ensembles."""

    def __init__(self, *, maxlen: int = 5_000) -> None:
        self._signals: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._ensembles: deque[dict[str, Any]] = deque(maxlen=maxlen)

    async def save_signal(self, snapshot: dict[str, Any]) -> None:
        self._signals.append(dict(snapshot))

    async def save_ensemble(self, snapshot: dict[str, Any]) -> None:
        self._ensembles.append(dict(snapshot))

    async def recent_signals(self, *, limit: int = 50) -> list[dict[str, Any]]:
        return list(reversed(list(self._signals)[-limit:]))

    async def recent_ensembles(self, *, limit: int = 50) -> list[dict[str, Any]]:
        return list(reversed(list(self._ensembles)[-limit:]))


class InMemoryPerformanceStore:
    """Holds raw outcomes per strategy and computes scorecards on demand."""

    def __init__(self, *, evaluator: SelfEvaluator | None = None, maxlen: int = 2_000) -> None:
        self._evaluator = evaluator or SelfEvaluator()
        self._outcomes: dict[str, deque[StrategyOutcome]] = {}
        self._maxlen = maxlen

    async def record_outcome(self, outcome: StrategyOutcome) -> None:
        bucket = self._outcomes.setdefault(outcome.strategy, deque(maxlen=self._maxlen))
        bucket.append(outcome)

    async def performance(self, strategy: str) -> StrategyPerformance | None:
        bucket = self._outcomes.get(strategy)
        if not bucket:
            return None
        return self._evaluator.evaluate(strategy, list(bucket))

    async def all_performance(self) -> dict[str, StrategyPerformance]:
        return {
            strategy: self._evaluator.evaluate(strategy, list(bucket))
            for strategy, bucket in self._outcomes.items()
            if bucket
        }
