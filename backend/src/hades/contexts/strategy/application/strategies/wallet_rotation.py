"""Wallet Rotation - trades the changing composition of the holder base.

Distinct from Smart Money Follow: this watches the *rotation* - smart money
flowing in while dumb money flows out (accumulation), or the reverse (distribution,
an exit). It reads the behavior member plus the smart/dumb wallet counts to judge
which way the holder base is turning over.
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


class WalletRotationStrategy(BaseStrategy):
    @classmethod
    def _describe(cls) -> StrategyMetadata:
        return StrategyMetadata(
            name="wallet_rotation",
            description="Reads holder-base rotation: smart-in/dumb-out buys, reverse exits.",
            priority=42,
            ideal_regimes=(MarketRegime.BULL, MarketRegime.SIDEWAYS, MarketRegime.FOMO),
            forbidden_regimes=(MarketRegime.PANIC,),
            features_used=("behavior", "wallet"),
            expected_holding_seconds=6000,
            historical_sharpe=1.2,
            profit_factor=1.5,
            win_rate=0.49,
            expectancy=0.29,
            lifecycle_stage=LifecycleStage.PRODUCTION,
        )

    def _evaluate(self, context: MarketContext) -> Evaluation:
        behavior = unit(context.member("behavior"))
        smart = context.smart_money_count
        dumb = context.dumb_money_count
        net_rotation = smart - dumb
        threshold = 0.55 / self.sensitivity

        if net_rotation > 0:
            conviction = clamp01(0.5 * behavior + 0.5 * clamp01(net_rotation / 5.0))
            if conviction >= threshold:
                return Evaluation(
                    signal_type=SignalType.BUY,
                    score=conviction,
                    headline="holder base rotating smart-in / dumb-out",
                    drivers=(f"net rotation +{net_rotation} wallets",),
                    influencing=("behavior", "smart_money_count", "dumb_money_count"),
                    favorable=("accumulation by better hands",),
                    risks=("rotation can stall",),
                )
        if net_rotation < 0 and dumb - smart >= 3:
            conviction = clamp01(0.5 * (1.0 - behavior) + 0.5 * clamp01((dumb - smart) / 5.0))
            return Evaluation(
                signal_type=SignalType.EXIT,
                score=conviction,
                headline="distribution: better hands leaving",
                drivers=(f"net rotation {net_rotation} wallets",),
                influencing=("behavior", "smart_money_count", "dumb_money_count"),
                risks=("smart money exiting into dumb money",),
            )
        return Evaluation(
            signal_type=SignalType.IGNORE,
            score=0.2,
            headline="holder base stable / unclear",
            influencing=("behavior",),
        )
