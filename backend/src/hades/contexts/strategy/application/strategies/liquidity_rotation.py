"""Liquidity Rotation - follows capital rotating into a name.

Meme-coin capital rotates in waves. This strategy fires when liquidity is both
healthy and improving relative to the broader tape (a risk-on rotation), corroborated
by momentum. It stands aside in low-liquidity and panic regimes where rotation is
really just flight.
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


class LiquidityRotationStrategy(BaseStrategy):
    @classmethod
    def _describe(cls) -> StrategyMetadata:
        return StrategyMetadata(
            name="liquidity_rotation",
            description="Follows risk-on liquidity rotating into a token.",
            priority=55,
            ideal_regimes=(MarketRegime.BULL, MarketRegime.FOMO),
            forbidden_regimes=(MarketRegime.LOW_LIQUIDITY, MarketRegime.PANIC, MarketRegime.BEAR),
            features_used=("liquidity", "momentum", "microstructure"),
            expected_holding_seconds=4800,
            historical_sharpe=1.1,
            profit_factor=1.45,
            win_rate=0.48,
            expectancy=0.27,
            lifecycle_stage=LifecycleStage.PRODUCTION,
        )

    def _evaluate(self, context: MarketContext) -> Evaluation:
        liquidity = unit(context.member("liquidity"))
        momentum = unit(context.member("momentum"))
        rotation = clamp01(0.5 + context.feature("liquidity_flow", 0.0) / 4.0)

        conviction = clamp01(0.45 * liquidity + 0.3 * rotation + 0.25 * momentum)
        threshold = 0.58 / self.sensitivity
        drivers = (
            f"liquidity {context.member('liquidity'):.0f}/100",
            f"momentum {context.member('momentum'):.0f}/100",
        )
        if conviction >= threshold and liquidity >= 0.5:
            return Evaluation(
                signal_type=SignalType.BUY,
                score=conviction,
                headline="liquidity rotating in (risk-on)",
                drivers=drivers,
                influencing=("liquidity", "liquidity_flow", "momentum"),
                favorable=("risk-on regime", "improving relative liquidity"),
                risks=("rotations reverse fast",),
            )
        return Evaluation(
            signal_type=SignalType.IGNORE,
            score=conviction,
            headline="no liquidity rotation",
            influencing=("liquidity", "momentum"),
        )
