"""Liquidity Expansion - enters when a pool's liquidity is deepening.

Deepening liquidity precedes durable moves: it lets size in and out without
slippage and signals real capital committing. Fires long when the liquidity read
is healthy and the committee expects a positive ROI. Stands aside in low-liquidity
regimes where "expansion" is an illusion.
"""

from __future__ import annotations

from hades.contexts.learning.domain.models import MarketRegime
from hades.contexts.strategy.application.base import BaseStrategy, Evaluation, clamp01, unit
from hades.contexts.strategy.domain.models import (
    LifecycleStage,
    MarketContext,
    SignalType,
    StrategyMetadata,
)


class LiquidityExpansionStrategy(BaseStrategy):
    @classmethod
    def _describe(cls) -> StrategyMetadata:
        return StrategyMetadata(
            name="liquidity_expansion",
            description="Enters tokens whose pool liquidity is deepening on real flow.",
            priority=25,
            ideal_regimes=(MarketRegime.BULL, MarketRegime.FOMO),
            forbidden_regimes=(MarketRegime.LOW_LIQUIDITY, MarketRegime.PANIC),
            features_used=("liquidity", "microstructure", "momentum"),
            expected_holding_seconds=3600,
            historical_sharpe=1.2,
            profit_factor=1.5,
            win_rate=0.5,
            expectancy=0.24,
            lifecycle_stage=LifecycleStage.PRODUCTION,
        )

    def _evaluate(self, context: MarketContext) -> Evaluation:
        liquidity = unit(context.member("liquidity"))
        microstructure = unit(context.member("microstructure"))
        roi = context.ai_prob_roi_positive

        conviction = clamp01(0.55 * liquidity + 0.20 * microstructure + 0.25 * roi)
        threshold = 0.58 / self.sensitivity
        drivers = (
            f"liquidity {context.member('liquidity'):.0f}/100",
            f"P(ROI+) {roi:.0%}",
        )
        if conviction >= threshold and roi >= 0.5:
            return Evaluation(
                signal_type=SignalType.BUY,
                score=conviction,
                headline="liquidity expanding on healthy flow",
                drivers=drivers,
                influencing=("liquidity", "microstructure", "ai_prob_roi_positive"),
                favorable=("deepening pool", "positive ROI probability"),
                risks=("liquidity can be mercenary and leave",),
            )
        return Evaluation(
            signal_type=SignalType.IGNORE,
            score=conviction,
            headline="liquidity not expanding convincingly",
            influencing=("liquidity",),
            risks=("thin/undirected liquidity",) if liquidity < 0.5 else (),
        )
