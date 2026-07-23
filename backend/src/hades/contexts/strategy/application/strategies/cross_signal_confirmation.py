"""Cross Signal Confirmation - the corroboration strategy.

A meta-strategy that fires only when *independent* facets agree: momentum, wallet
quality, liquidity, security and the committee's own lean all pointing the same
way. Its conviction is a function of how many facets confirm, so it is quiet on
mixed evidence and loud on unanimity. High priority - a confirmed setup is the
platform's strongest tell.
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


class CrossSignalConfirmationStrategy(BaseStrategy):
    @classmethod
    def _describe(cls) -> StrategyMetadata:
        return StrategyMetadata(
            name="cross_signal_confirmation",
            description="Fires only when multiple independent facets confirm the same direction.",
            priority=5,
            ideal_regimes=(MarketRegime.BULL, MarketRegime.FOMO, MarketRegime.SIDEWAYS),
            forbidden_regimes=(MarketRegime.PANIC,),
            features_used=("momentum", "wallet", "liquidity", "security"),
            expected_holding_seconds=3600,
            historical_sharpe=1.8,
            profit_factor=2.0,
            win_rate=0.55,
            expectancy=0.45,
            lifecycle_stage=LifecycleStage.PRODUCTION,
        )

    def _evaluate(self, context: MarketContext) -> Evaluation:
        facets = {
            "momentum": context.member("momentum") >= 58.0,
            "wallet": context.wallet_score >= 58.0,
            "liquidity": context.member("liquidity") >= 55.0,
            "security": context.security_score >= 60.0,
            "ai_edge": context.ai_expected_edge > 0.05,
        }
        confirmed = [name for name, ok in facets.items() if ok]
        agreement = len(confirmed) / len(facets)

        strength = clamp01(
            0.2 * unit(context.member("momentum"))
            + 0.2 * unit(context.wallet_score)
            + 0.2 * unit(context.member("liquidity"))
            + 0.2 * unit(context.security_score)
            + 0.2 * (0.5 + max(0.0, context.ai_expected_edge))
        )
        conviction = clamp01(0.5 * agreement + 0.5 * strength)
        min_confirmed = max(2, round(3 / self.sensitivity))

        if len(confirmed) >= min_confirmed and agreement >= 0.6:
            return Evaluation(
                signal_type=SignalType.BUY,
                score=conviction,
                headline=f"{len(confirmed)}/{len(facets)} facets confirm long",
                drivers=(f"confirmed: {', '.join(confirmed)}",),
                influencing=tuple(facets.keys()),
                favorable=("independent confirmation across facets",),
                risks=("correlated facets can confirm a false positive",),
            )
        return Evaluation(
            signal_type=SignalType.IGNORE,
            score=conviction,
            headline=f"insufficient confirmation ({len(confirmed)}/{len(facets)})",
            influencing=tuple(facets.keys()),
            risks=("mixed evidence",),
        )
