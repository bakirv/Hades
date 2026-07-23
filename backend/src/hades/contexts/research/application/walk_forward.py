"""Walk-Forward Engine — rolling out-of-sample validation.

The only honest test of a strategy: fit (or simply measure) on a training window,
then score on the *next, unseen* window, and roll forward. Aggregate out-of-sample
performance — and its ratio to in-sample (the efficiency) — tells you whether an
edge survives contact with data it never saw. A high in-sample score that decays
out-of-sample is the classic signature of overfitting.
"""

from __future__ import annotations

from collections.abc import Sequence

from hades.contexts.research.application import metrics as m
from hades.contexts.research.application.backtest_engine import BacktestingEngine
from hades.contexts.research.domain.models import (
    MarketConditions,
    PerformanceMetrics,
    StrategyGenome,
    TradeRecord,
    WalkForwardResult,
    WalkForwardWindow,
    safe_div,
)
from hades.contexts.research.domain.ports import HistoricalSample


class WalkForwardEngine:
    """Splits history into rolling train/test folds and validates a genome."""

    def __init__(self, backtester: BacktestingEngine | None = None) -> None:
        self._bt = backtester or BacktestingEngine()

    def run(
        self,
        *,
        strategy: str,
        genome: StrategyGenome,
        samples: Sequence[HistoricalSample],
        folds: int = 4,
        conditions: MarketConditions | None = None,
    ) -> WalkForwardResult:
        conditions = conditions or MarketConditions()
        n = len(samples)
        folds = max(2, folds)
        if n < folds * 2:
            # Not enough data to split — report a single degenerate window.
            oos = self._bt.run(
                strategy=strategy, genome=genome, samples=samples, conditions=conditions
            ).metrics
            return WalkForwardResult(strategy=strategy, aggregate_oos=oos, efficiency=1.0)

        fold_size = n // (folds + 1)
        windows: list[WalkForwardWindow] = []
        oos_trades: list[TradeRecord] = []
        is_returns: list[float] = []
        oos_returns: list[float] = []

        for i in range(folds):
            train_end = fold_size * (i + 1)
            test_end = min(train_end + fold_size, n)
            train = samples[:train_end]
            test = samples[train_end:test_end]
            if not test:
                break
            is_result = self._bt.run(
                strategy=strategy, genome=genome, samples=train, conditions=conditions
            )
            oos_result = self._bt.run(
                strategy=strategy, genome=genome, samples=test, conditions=conditions
            )
            windows.append(
                WalkForwardWindow(
                    index=i,
                    train_from=str(0),
                    train_to=str(train_end),
                    test_from=str(train_end),
                    test_to=str(test_end),
                    in_sample=is_result.metrics,
                    out_of_sample=oos_result.metrics,
                )
            )
            is_returns.append(is_result.metrics.total_return)
            oos_returns.append(oos_result.metrics.total_return)
            # Rebuild the OOS trades so the aggregate scorecard is exact.
            from hades.contexts.research.application.backtest_engine import apply_frictions
            from hades.contexts.research.application.strategies import evaluate

            oos_trades.extend(apply_frictions(evaluate(genome, test), test, conditions))

        aggregate: PerformanceMetrics = m.compute(oos_trades)
        mean_is = safe_div(sum(is_returns), len(is_returns))
        mean_oos = safe_div(sum(oos_returns), len(oos_returns))
        efficiency = safe_div(mean_oos, mean_is, default=0.0) if mean_is > 0 else 0.0
        return WalkForwardResult(
            strategy=strategy,
            windows=tuple(windows),
            aggregate_oos=aggregate,
            efficiency=round(efficiency, 4),
        )
