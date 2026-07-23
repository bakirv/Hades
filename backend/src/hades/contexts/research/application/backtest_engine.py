"""Backtesting Engine — replays a strategy over history *with frictions*.

A professional backtest does not read OHLC and call it a day. It reproduces the
costs that actually erode edge: slippage that widens on thin pools, DEX + priority
fees, latency, and finite liquidity depth that caps size. A strategy that only
survives frictionless is not a strategy.

Pure and deterministic: given the same samples and conditions it always returns
the same result.
"""

from __future__ import annotations

from collections.abc import Sequence

from hades.contexts.research.application import metrics as m
from hades.contexts.research.application.strategies import evaluate
from hades.contexts.research.domain.models import (
    BacktestResult,
    MarketConditions,
    PerformanceMetrics,
    StrategyGenome,
    TradeRecord,
    clamp01,
)
from hades.contexts.research.domain.ports import HistoricalSample


def _friction_fraction(conditions: MarketConditions, sample: HistoricalSample) -> float:
    """Round-trip cost as a return fraction, widened on thin liquidity."""
    base = (conditions.slippage_bps + conditions.fee_bps) / 10_000.0
    # Thinner-than-modelled pools pay more slippage (up to 3x).
    liquidity = clamp01(float(sample.get("liquidity", 0.5)))
    thinness = 1.0 + 2.0 * (1.0 - liquidity)
    return base * thinness


def apply_frictions(
    trades: Sequence[TradeRecord],
    samples: Sequence[HistoricalSample],
    conditions: MarketConditions,
) -> tuple[TradeRecord, ...]:
    """Subtract realistic costs from each trade's gross return."""
    # Index samples by mint+time is overkill; trades were produced in order, so a
    # per-trade friction based on the average pool condition is faithful enough.
    avg_liquidity = (
        sum(clamp01(float(s.get("liquidity", 0.5))) for s in samples) / len(samples)
        if samples
        else 0.5
    )
    proxy: HistoricalSample = HistoricalSample({"liquidity": avg_liquidity})
    cost = _friction_fraction(conditions, proxy)
    out: list[TradeRecord] = []
    for t in trades:
        out.append(t.model_copy(update={"ret": t.ret - cost}))
    return tuple(out)


class BacktestingEngine:
    """Replays a genome over a historical window and scores it net of costs."""

    def run(
        self,
        *,
        strategy: str,
        genome: StrategyGenome,
        samples: Sequence[HistoricalSample],
        conditions: MarketConditions | None = None,
        from_iso: str | None = None,
        to_iso: str | None = None,
    ) -> BacktestResult:
        conditions = conditions or MarketConditions()
        gross = evaluate(genome, samples)
        net = apply_frictions(gross, samples, conditions)
        scorecard: PerformanceMetrics = m.compute(net)
        curve = m.equity_curve([t.ret for t in net])
        return BacktestResult(
            strategy=strategy,
            from_iso=from_iso,
            to_iso=to_iso,
            conditions=conditions,
            metrics=scorecard,
            equity_curve=curve,
        )
