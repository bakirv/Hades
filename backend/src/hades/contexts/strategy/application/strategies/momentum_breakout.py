"""Momentum Breakout - rides tokens accelerating out of a base.

Fires long when the committee's momentum read is strong, the market lean (P(TP) -
P(SL)) is positive and volatility confirms a real expansion (not noise). It has no
business in a panic or a bear tape, where breakouts fail - those regimes are on
its forbidden list.
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


class MomentumBreakoutStrategy(BaseStrategy):
    @classmethod
    def _describe(cls) -> StrategyMetadata:
        return StrategyMetadata(
            name="momentum_breakout",
            description="Rides tokens breaking out of a base with expanding momentum.",
            priority=10,
            ideal_regimes=(MarketRegime.BULL, MarketRegime.FOMO),
            forbidden_regimes=(MarketRegime.PANIC, MarketRegime.BEAR),
            features_used=("momentum", "volatility", "microstructure"),
            expected_holding_seconds=1800,
            historical_sharpe=1.4,
            profit_factor=1.6,
            win_rate=0.46,
            expectancy=0.32,
            lifecycle_stage=LifecycleStage.PRODUCTION,
        )

    def _evaluate(self, context: MarketContext) -> Evaluation:
        momentum = unit(context.member("momentum"))
        volatility = unit(context.member("volatility"))
        microstructure = unit(context.member("microstructure"))
        edge = max(0.0, context.ai_expected_edge)

        conviction = clamp01(0.55 * momentum + 0.25 * edge + 0.20 * microstructure)
        # Punish breakouts on dead volatility (nothing to ride).
        conviction *= 0.6 + 0.4 * min(1.0, volatility / 0.5)
        threshold = 0.55 / self.sensitivity

        drivers = (
            f"momentum {context.member('momentum'):.0f}/100",
            f"AI edge {context.ai_expected_edge:+.2f}",
        )
        if conviction >= threshold and edge > 0:
            return Evaluation(
                signal_type=SignalType.BUY,
                score=conviction,
                headline="momentum breakout confirmed",
                drivers=drivers,
                influencing=("momentum", "volatility", "microstructure", "ai_expected_edge"),
                favorable=("bull/FOMO regime", "expanding volatility"),
                risks=("breakout can fail into a fade",),
            )
        return Evaluation(
            signal_type=SignalType.IGNORE,
            score=conviction,
            headline="no breakout: momentum/edge insufficient",
            influencing=("momentum", "ai_expected_edge"),
            risks=("weak momentum",) if momentum < 0.5 else (),
        )
