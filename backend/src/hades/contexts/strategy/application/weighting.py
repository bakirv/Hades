"""DynamicWeightEngine - how much to trust each strategy right now.

Weight is *never fixed*. It is a base prior (from the strategy's priority) scaled
by legible factors: how well the strategy fits the current market regime, its
recent Sharpe and Profit Factor, its drawdown, its consistency, how many trades
back the estimate, the AI's confidence in this token, and any Research-Lab boost.
The result is floored above zero - a weak strategy is muted, never removed - and
every factor is retained on the :class:`StrategyWeight` so the dashboard can show
*why* a strategy weighs what it does.
"""

from __future__ import annotations

from hades.contexts.learning.domain.models import MarketRegime
from hades.contexts.strategy.application.base import BaseStrategy, clamp01
from hades.contexts.strategy.domain.models import (
    MarketContext,
    StrategyMetadata,
    StrategyPerformance,
    StrategyWeight,
)

#: A strategy is muted this low, never to zero - always able to recover.
WEIGHT_FLOOR = 0.05


class DynamicWeightEngine:
    """Computes a per-strategy :class:`StrategyWeight` from context + performance."""

    def __init__(
        self,
        *,
        weight_floor: float = WEIGHT_FLOOR,
        regime_boost: float = 1.4,
        regime_penalty: float = 0.5,
    ) -> None:
        self._floor = weight_floor
        self._regime_boost = regime_boost
        self._regime_penalty = regime_penalty

    def compute(
        self,
        strategy: BaseStrategy,
        context: MarketContext,
        performance: StrategyPerformance | None,
        *,
        research_boost: float = 1.0,
    ) -> StrategyWeight:
        meta = strategy.metadata
        base = _priority_base(meta.priority)
        regime_factor = self._regime_factor(meta, context.regime)
        sharpe_factor = _sharpe_factor(meta, performance)
        pf_factor = _profit_factor_factor(meta, performance)
        drawdown_factor = _drawdown_factor(meta, performance)
        consistency_factor = _consistency_factor(performance)
        sample_factor = _sample_factor(performance)
        ai_factor = _ai_factor(context)
        research_factor = max(0.25, min(2.0, research_boost))

        raw = (
            base
            * regime_factor
            * sharpe_factor
            * pf_factor
            * drawdown_factor
            * consistency_factor
            * sample_factor
            * ai_factor
            * research_factor
        )
        weight = max(self._floor, round(raw, 5))
        return StrategyWeight(
            strategy=meta.name,
            weight=weight,
            base=round(base, 4),
            regime_factor=round(regime_factor, 4),
            sharpe_factor=round(sharpe_factor, 4),
            profit_factor_factor=round(pf_factor, 4),
            drawdown_factor=round(drawdown_factor, 4),
            consistency_factor=round(consistency_factor, 4),
            sample_factor=round(sample_factor, 4),
            ai_factor=round(ai_factor, 4),
            research_factor=round(research_factor, 4),
            reason=_reason(meta, context, performance, regime_factor),
        )

    def _regime_factor(self, meta: StrategyMetadata, regime: MarketRegime) -> float:
        if regime in meta.forbidden_regimes:
            return self._regime_penalty * 0.5
        if regime in meta.ideal_regimes:
            return self._regime_boost
        return 1.0


def _priority_base(priority: int) -> float:
    """Lower priority number => higher base weight prior (0.6 ... 1.5)."""
    p = max(1, min(200, priority))
    return round(1.5 - (p / 200.0) * 0.9, 4)


def _sharpe_factor(meta: StrategyMetadata, perf: StrategyPerformance | None) -> float:
    sharpe = perf.sharpe if perf and perf.trades >= 3 else meta.historical_sharpe
    # Map Sharpe (~ -1 ... 3) into a 0.6 ... 1.5 multiplier.
    return round(max(0.6, min(1.5, 1.0 + sharpe * 0.2)), 4)


def _profit_factor_factor(meta: StrategyMetadata, perf: StrategyPerformance | None) -> float:
    pf = perf.profit_factor if perf and perf.trades >= 3 else meta.profit_factor
    return round(max(0.5, min(1.6, 0.6 + pf * 0.4)), 4)


def _drawdown_factor(meta: StrategyMetadata, perf: StrategyPerformance | None) -> float:
    if perf and perf.trades >= 5 and perf.net_pnl_usd != 0.0:
        # Deeper drawdown relative to net PnL => stronger penalty.
        ratio = perf.max_drawdown_usd / (abs(perf.net_pnl_usd) + 1e-9)
        return round(max(0.5, min(1.0, 1.0 - 0.4 * clamp01(ratio))), 4)
    dd = meta.historical_drawdown  # fraction
    return round(max(0.5, 1.0 - dd), 4)


def _consistency_factor(perf: StrategyPerformance | None) -> float:
    if not perf or perf.trades < 3:
        return 1.0
    if perf.degraded:
        return 0.6
    return round(0.85 + 0.3 * clamp01(perf.win_rate), 4)


def _sample_factor(perf: StrategyPerformance | None) -> float:
    """Shrink toward the prior when few trades back the estimate (confidence)."""
    trades = perf.trades if perf else 0
    return round(0.7 + 0.3 * clamp01(trades / 30.0), 4)


def _ai_factor(context: MarketContext) -> float:
    return round(0.7 + 0.6 * clamp01(context.ai_confidence), 4)


def _reason(
    meta: StrategyMetadata,
    context: MarketContext,
    perf: StrategyPerformance | None,
    regime_factor: float,
) -> str:
    bits = [f"base@priority{meta.priority}"]
    if regime_factor > 1.0:
        bits.append(f"regime {context.regime.value} favourable")
    elif regime_factor < 1.0:
        bits.append(f"regime {context.regime.value} unfavourable")
    if perf and perf.trades >= 3:
        bits.append(f"PF {perf.profit_factor:.2f}, WR {perf.win_rate:.0%}")
        if perf.degraded:
            bits.append("DEGRADED -> tapered")
    else:
        bits.append("using historical priors")
    return "; ".join(bits)
