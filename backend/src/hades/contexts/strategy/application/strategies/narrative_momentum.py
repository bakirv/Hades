"""Narrative Momentum - trades tokens riding an active meta/narrative.

Narratives (a theme, a trend, a meta) drive meme flows. When a token is attached
to a live narrative and momentum confirms attention is flowing to it, this strategy
buys the story. With no narrative attached it simply abstains - it never invents a
thesis where there is none.
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


class NarrativeMomentumStrategy(BaseStrategy):
    @classmethod
    def _describe(cls) -> StrategyMetadata:
        return StrategyMetadata(
            name="narrative_momentum",
            description="Buys tokens riding an active narrative with confirming momentum.",
            priority=60,
            ideal_regimes=(MarketRegime.FOMO, MarketRegime.BULL),
            forbidden_regimes=(MarketRegime.PANIC, MarketRegime.BEAR),
            features_used=("momentum", "microstructure", "narrative"),
            expected_holding_seconds=5400,
            historical_sharpe=1.0,
            profit_factor=1.5,
            win_rate=0.45,
            expectancy=0.36,
            lifecycle_stage=LifecycleStage.PRODUCTION,
        )

    def _evaluate(self, context: MarketContext) -> Evaluation:
        if not context.narrative:
            return Evaluation(
                signal_type=SignalType.IGNORE,
                score=0.1,
                headline="no active narrative attached",
                influencing=("narrative",),
            )
        momentum = unit(context.member("momentum"))
        strength = clamp01(0.5 + context.feature("narrative_strength", 0.0) / 2.0)

        conviction = clamp01(0.55 * momentum + 0.45 * strength)
        threshold = 0.57 / self.sensitivity
        drivers = (
            f"narrative '{context.narrative}'",
            f"momentum {context.member('momentum'):.0f}/100",
        )
        if conviction >= threshold and momentum >= 0.5:
            return Evaluation(
                signal_type=SignalType.BUY,
                score=conviction,
                headline=f"narrative momentum: {context.narrative}",
                drivers=drivers,
                influencing=("narrative", "narrative_strength", "momentum"),
                favorable=("live narrative", "attention flowing in"),
                risks=("narratives rotate and fade abruptly",),
            )
        return Evaluation(
            signal_type=SignalType.IGNORE,
            score=conviction,
            headline="narrative present but momentum weak",
            influencing=("narrative", "momentum"),
        )
