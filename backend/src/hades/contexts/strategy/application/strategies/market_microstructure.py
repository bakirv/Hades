"""Market Microstructure - reads the fine-grained shape of order flow.

Trades the quality of the tape itself: tight, orderly buying is bullish; a
deteriorating microstructure (thinning book, one-sided selling) is a reason to
leave. This is the one strategy that will readily emit an EXIT when the structure
turns, not just a BUY when it is healthy.
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


class MarketMicrostructureStrategy(BaseStrategy):
    @classmethod
    def _describe(cls) -> StrategyMetadata:
        return StrategyMetadata(
            name="market_microstructure",
            description="Trades the health of the order-flow microstructure; exits when it decays.",
            priority=40,
            ideal_regimes=(MarketRegime.BULL, MarketRegime.SIDEWAYS, MarketRegime.FOMO),
            forbidden_regimes=(MarketRegime.LOW_LIQUIDITY,),
            features_used=("microstructure", "liquidity", "volatility"),
            expected_holding_seconds=1200,
            historical_sharpe=1.3,
            profit_factor=1.5,
            win_rate=0.51,
            expectancy=0.22,
            lifecycle_stage=LifecycleStage.PRODUCTION,
        )

    def _evaluate(self, context: MarketContext) -> Evaluation:
        microstructure = context.member("microstructure")
        structure = unit(microstructure)
        liquidity = unit(context.member("liquidity"))
        buy_threshold = 0.58 / self.sensitivity

        conviction = clamp01(0.7 * structure + 0.3 * liquidity)
        drivers = (f"microstructure {microstructure:.0f}/100",)
        if conviction >= buy_threshold:
            return Evaluation(
                signal_type=SignalType.BUY,
                score=conviction,
                headline="orderly, healthy microstructure",
                drivers=drivers,
                influencing=("microstructure", "liquidity"),
                favorable=("tight, one-directional buying", "adequate liquidity"),
                risks=("microstructure can flip quickly",),
            )
        if microstructure <= 30.0:
            return Evaluation(
                signal_type=SignalType.EXIT,
                score=clamp01(1.0 - structure),
                headline="microstructure deteriorating - reduce",
                drivers=(f"microstructure {microstructure:.0f}/100",),
                influencing=("microstructure",),
                risks=("thinning book / one-sided selling",),
            )
        return Evaluation(
            signal_type=SignalType.IGNORE,
            score=conviction,
            headline="microstructure neutral",
            influencing=("microstructure",),
        )
