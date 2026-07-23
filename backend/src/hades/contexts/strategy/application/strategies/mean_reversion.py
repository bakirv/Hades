"""Mean Reversion - fades exhaustion, never a trend.

In range-bound tape, extremes revert. This strategy buys statistical oversold and
flags overbought exhaustion as an EXIT. It is explicitly *forbidden* from trading
strong bull/FOMO regimes - fading a real trend is how mean-reversion books blow
up - which is encoded in its forbidden-regimes list.
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


class MeanReversionStrategy(BaseStrategy):
    @classmethod
    def _describe(cls) -> StrategyMetadata:
        return StrategyMetadata(
            name="mean_reversion",
            description="Fades exhaustion in range-bound tape; never fights a trend.",
            priority=45,
            ideal_regimes=(MarketRegime.SIDEWAYS, MarketRegime.LOW_LIQUIDITY),
            forbidden_regimes=(MarketRegime.BULL, MarketRegime.FOMO, MarketRegime.PANIC),
            features_used=("momentum", "volatility", "microstructure"),
            expected_holding_seconds=1800,
            historical_sharpe=0.9,
            profit_factor=1.35,
            win_rate=0.58,
            expectancy=0.15,
            lifecycle_stage=LifecycleStage.PRODUCTION,
        )

    def _evaluate(self, context: MarketContext) -> Evaluation:
        momentum = context.member("momentum")
        volatility = unit(context.member("volatility"))
        threshold = 0.55 / self.sensitivity

        # Oversold: very low momentum in a non-trending regime -> revert up.
        if momentum <= 30.0:
            conviction = clamp01((0.30 - unit(momentum)) * 2.0 + 0.3 * volatility)
            if conviction >= threshold:
                return Evaluation(
                    signal_type=SignalType.BUY,
                    score=conviction,
                    headline="oversold reversion setup",
                    drivers=(f"momentum {momentum:.0f}/100 (oversold)",),
                    influencing=("momentum", "volatility"),
                    favorable=("range-bound regime", "stretched to the downside"),
                    risks=("oversold can get more oversold",),
                )
        # Overbought exhaustion: flag an exit, don't short a meme into strength.
        if momentum >= 78.0:
            conviction = clamp01((unit(momentum) - 0.75) * 2.0 + 0.3 * volatility)
            return Evaluation(
                signal_type=SignalType.EXIT,
                score=conviction,
                headline="overbought exhaustion - take profit",
                drivers=(f"momentum {momentum:.0f}/100 (overbought)",),
                influencing=("momentum", "volatility"),
                risks=("trend may extend past the extreme",),
            )
        return Evaluation(
            signal_type=SignalType.IGNORE,
            score=0.2,
            headline="no reversion extreme",
            influencing=("momentum",),
        )
