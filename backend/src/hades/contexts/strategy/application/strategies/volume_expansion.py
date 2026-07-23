"""Volume Expansion - enters on a genuine surge in trade activity.

Volume precedes price. When microstructure (trade intensity) and momentum both
lift together, real demand is arriving. The strategy separates a true surge from a
single-print spike by requiring momentum to corroborate the microstructure read.
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


class VolumeExpansionStrategy(BaseStrategy):
    @classmethod
    def _describe(cls) -> StrategyMetadata:
        return StrategyMetadata(
            name="volume_expansion",
            description="Enters on corroborated surges in trade volume/intensity.",
            priority=35,
            ideal_regimes=(MarketRegime.BULL, MarketRegime.FOMO, MarketRegime.HIGHLY_VOLATILE),
            forbidden_regimes=(MarketRegime.PANIC, MarketRegime.LOW_LIQUIDITY),
            features_used=("microstructure", "momentum", "liquidity"),
            expected_holding_seconds=2400,
            historical_sharpe=1.15,
            profit_factor=1.45,
            win_rate=0.47,
            expectancy=0.26,
            lifecycle_stage=LifecycleStage.PRODUCTION,
        )

    def _evaluate(self, context: MarketContext) -> Evaluation:
        microstructure = unit(context.member("microstructure"))
        momentum = unit(context.member("momentum"))
        volume_feat = context.feature("volume_zscore", 0.0)
        surge = clamp01(0.5 * microstructure + 0.5 * clamp01(0.5 + volume_feat / 4.0))

        conviction = clamp01(0.6 * surge + 0.4 * momentum)
        threshold = 0.57 / self.sensitivity
        drivers = (
            f"trade intensity {context.member('microstructure'):.0f}/100",
            f"momentum {context.member('momentum'):.0f}/100",
        )
        if conviction >= threshold and momentum >= 0.5:
            return Evaluation(
                signal_type=SignalType.BUY,
                score=conviction,
                headline="volume expanding with momentum",
                drivers=drivers,
                influencing=("microstructure", "momentum", "volume_zscore"),
                favorable=("rising trade intensity", "corroborating momentum"),
                risks=("volume spikes can be wash/one-off",),
            )
        return Evaluation(
            signal_type=SignalType.IGNORE,
            score=conviction,
            headline="no corroborated volume surge",
            influencing=("microstructure", "momentum"),
            risks=("uncorroborated volume",) if momentum < 0.5 else (),
        )
