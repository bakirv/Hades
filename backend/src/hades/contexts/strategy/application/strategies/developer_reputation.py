"""Developer Reputation - weights a token by who shipped it.

Deployer track record is one of the most durable edges in meme coins: serial
ruggers repeat, and credible builders repeat too. This strategy fires long only
when the developer read is strong; a poor reputation yields an explicit abstention
(it is effectively a veto, never a short).
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


class DeveloperReputationStrategy(BaseStrategy):
    @classmethod
    def _describe(cls) -> StrategyMetadata:
        return StrategyMetadata(
            name="developer_reputation",
            description="Buys tokens from credible deployers; abstains on poor reputations.",
            priority=28,
            ideal_regimes=(MarketRegime.BULL, MarketRegime.FOMO, MarketRegime.SIDEWAYS),
            forbidden_regimes=(MarketRegime.PANIC,),
            features_used=("developer", "security", "wallet"),
            expected_holding_seconds=7200,
            historical_sharpe=1.25,
            profit_factor=1.6,
            win_rate=0.5,
            expectancy=0.33,
            lifecycle_stage=LifecycleStage.PRODUCTION,
        )

    def _evaluate(self, context: MarketContext) -> Evaluation:
        developer = context.developer_score
        dev = unit(developer)
        security = unit(context.security_score)

        conviction = clamp01(0.65 * dev + 0.35 * security)
        threshold = 0.6 / self.sensitivity
        drivers = (f"developer reputation {developer:.0f}/100",)
        if conviction >= threshold and developer >= 60.0:
            return Evaluation(
                signal_type=SignalType.BUY,
                score=conviction,
                headline="credible developer track record",
                drivers=drivers,
                influencing=("developer", "security"),
                favorable=("proven deployer", "clean security"),
                risks=("even good devs can abandon a launch",),
            )
        return Evaluation(
            signal_type=SignalType.IGNORE,
            score=conviction,
            headline="developer reputation insufficient",
            influencing=("developer",),
            risks=("weak/unknown deployer history",) if developer < 45.0 else (),
        )
