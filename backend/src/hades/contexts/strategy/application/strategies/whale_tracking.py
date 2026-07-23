"""Whale Tracking - trades the footprint of large, credible holders.

A concentrated but *credible* holder base (trusted whales, not a rug cluster) can
front-run demand. This strategy fires long when wallet trust is high and holder
concentration is elevated-but-not-extreme; extreme concentration is a risk, not a
green light, so conviction is dampened as the largest cluster grows.
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


class WhaleTrackingStrategy(BaseStrategy):
    @classmethod
    def _describe(cls) -> StrategyMetadata:
        return StrategyMetadata(
            name="whale_tracking",
            description="Tracks credible whale accumulation; penalises rug-like concentration.",
            priority=30,
            ideal_regimes=(MarketRegime.BULL, MarketRegime.FOMO),
            forbidden_regimes=(MarketRegime.PANIC, MarketRegime.BEAR),
            features_used=("wallet", "holder_distribution", "security"),
            expected_holding_seconds=5400,
            historical_sharpe=1.1,
            profit_factor=1.4,
            win_rate=0.44,
            expectancy=0.28,
            lifecycle_stage=LifecycleStage.PRODUCTION,
        )

    def _evaluate(self, context: MarketContext) -> Evaluation:
        wallet = unit(context.member("wallet"))
        # holder_distribution is 100 when healthy (dispersed); invert for concentration.
        concentration = 1.0 - unit(context.member("holder_distribution", 60.0))
        cluster = clamp01(context.largest_cluster_pct / 100.0)
        # A little concentration helps (whales lead); too much is a rug tell.
        concentration_bonus = max(0.0, 0.4 - abs(concentration - 0.35))
        rug_penalty = max(0.0, cluster - 0.5)

        conviction = clamp01(0.6 * wallet + concentration_bonus - rug_penalty)
        threshold = 0.55 / self.sensitivity
        drivers = (
            f"wallet trust {context.member('wallet'):.0f}/100",
            f"largest cluster {context.largest_cluster_pct:.0f}%",
        )
        if conviction >= threshold and rug_penalty == 0.0:
            return Evaluation(
                signal_type=SignalType.BUY,
                score=conviction,
                headline="credible whale accumulation",
                drivers=drivers,
                influencing=("wallet", "holder_distribution", "largest_cluster_pct"),
                favorable=("trusted large holders", "moderate concentration"),
                risks=("whales can dump; watch cluster growth",),
            )
        return Evaluation(
            signal_type=SignalType.IGNORE,
            score=conviction,
            headline="whale profile not favourable",
            influencing=("wallet", "largest_cluster_pct"),
            risks=("dangerous holder concentration",) if rug_penalty > 0 else (),
        )
