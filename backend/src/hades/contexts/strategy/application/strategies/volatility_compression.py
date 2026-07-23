"""Volatility Compression - positions ahead of an expansion.

Coiled, low-volatility ranges precede violent moves. This strategy buys the quiet
before the storm: low volatility, adequate liquidity and a mildly positive
committee lean. It leans into range regimes and sits out regimes that are already
volatile (there is nothing left to compress).
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


class VolatilityCompressionStrategy(BaseStrategy):
    @classmethod
    def _describe(cls) -> StrategyMetadata:
        return StrategyMetadata(
            name="volatility_compression",
            description="Positions ahead of a breakout while volatility is compressed.",
            priority=50,
            ideal_regimes=(MarketRegime.SIDEWAYS,),
            forbidden_regimes=(MarketRegime.HIGHLY_VOLATILE, MarketRegime.PANIC),
            features_used=("volatility", "liquidity", "momentum"),
            expected_holding_seconds=3600,
            historical_sharpe=1.05,
            profit_factor=1.4,
            win_rate=0.43,
            expectancy=0.34,
            lifecycle_stage=LifecycleStage.PRODUCTION,
        )

    def _evaluate(self, context: MarketContext) -> Evaluation:
        volatility = context.member("volatility")
        compression = 1.0 - unit(volatility)  # low vol -> high compression
        liquidity = unit(context.member("liquidity"))
        lean = max(0.0, context.ai_expected_edge)

        conviction = clamp01(0.55 * compression + 0.25 * liquidity + 0.20 * (0.5 + lean))
        threshold = 0.58 / self.sensitivity
        drivers = (
            f"volatility {volatility:.0f}/100 (compressed)",
            f"liquidity {context.member('liquidity'):.0f}/100",
        )
        if conviction >= threshold and volatility <= 45.0:
            return Evaluation(
                signal_type=SignalType.BUY,
                score=conviction,
                headline="volatility compressed - expansion likely",
                drivers=drivers,
                influencing=("volatility", "liquidity", "ai_expected_edge"),
                favorable=("coiled range", "liquidity to fuel a move"),
                risks=("compression can persist longer than expected",),
            )
        return Evaluation(
            signal_type=SignalType.IGNORE,
            score=conviction,
            headline="no compression setup",
            influencing=("volatility",),
            risks=("already expanded",) if volatility > 45.0 else (),
        )
