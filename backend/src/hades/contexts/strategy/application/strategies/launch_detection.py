"""Launch Detection - catches clean launches in their first minutes.

The earliest, highest-variance window. This strategy leans on the committee's
timing read (freshness) but demands a clean security verdict and a liquidity floor
before it will touch a brand-new token - most launches are traps, so the bar for
security is deliberately high.
"""

from __future__ import annotations

from typing import Any

from hades.contexts.learning.domain.models import MarketRegime
from hades.contexts.strategy.application.base import BaseStrategy, Evaluation, clamp01, unit
from hades.contexts.strategy.domain.models import (
    LifecycleStage,
    MarketContext,
    MarketValidation,
    SignalType,
    StrategyMetadata,
)


class LaunchDetectionStrategy(BaseStrategy):
    @classmethod
    def _describe(cls) -> StrategyMetadata:
        return StrategyMetadata(
            name="launch_detection",
            description="Catches clean token launches early, gated hard on security.",
            priority=20,
            ideal_regimes=(MarketRegime.FOMO, MarketRegime.BULL, MarketRegime.HIGHLY_VOLATILE),
            forbidden_regimes=(MarketRegime.PANIC, MarketRegime.BEAR),
            features_used=("timing", "security", "liquidity"),
            expected_holding_seconds=900,
            historical_sharpe=1.0,
            profit_factor=1.5,
            win_rate=0.4,
            expectancy=0.5,
            lifecycle_stage=LifecycleStage.PRODUCTION,
        )

    def load_configuration(self, params: dict[str, Any]) -> None:
        # A prudent default security floor unless the operator lowers it.
        params = {"min_security_score": 65.0, **params}
        super().load_configuration(params)

    def validate_market(self, context: MarketContext) -> MarketValidation:
        base = super().validate_market(context)
        if not base.ok:
            return base
        floor = float(self._params.get("min_security_score", 65.0))
        if context.security_score < floor:
            return MarketValidation(ok=False, reason=f"launch needs security >= {floor:.0f}")
        return base

    def _evaluate(self, context: MarketContext) -> Evaluation:
        timing = unit(context.member("timing"))
        liquidity = unit(context.member("liquidity"))
        security = unit(context.security_score)

        conviction = clamp01(0.5 * timing + 0.25 * liquidity + 0.25 * security)
        threshold = 0.55 / self.sensitivity
        drivers = (
            f"timing/freshness {context.member('timing'):.0f}/100",
            f"security {context.security_score:.0f}/100",
        )
        if conviction >= threshold and timing >= 0.55:
            return Evaluation(
                signal_type=SignalType.BUY,
                score=conviction,
                headline="clean early launch detected",
                drivers=drivers,
                influencing=("timing", "security", "liquidity"),
                favorable=("fresh launch", "security cleared", "liquidity present"),
                risks=("early launches are high-variance",),
            )
        return Evaluation(
            signal_type=SignalType.IGNORE,
            score=conviction,
            headline="not a clean early launch",
            influencing=("timing", "security"),
            risks=("stale or unproven launch",) if timing < 0.55 else (),
        )
