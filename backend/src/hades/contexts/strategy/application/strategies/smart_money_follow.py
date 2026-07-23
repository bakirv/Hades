"""Smart Money Follow - piggybacks wallets with a proven edge.

The Wallet Intelligence context labels wallets by realised skill. When trusted
"smart money" is accumulating a token and few "dumb money" wallets are, this
strategy follows them. Its conviction scales with the wallet read and the count of
smart holders; it never fires when security has not cleared.
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


class SmartMoneyFollowStrategy(BaseStrategy):
    @classmethod
    def _describe(cls) -> StrategyMetadata:
        return StrategyMetadata(
            name="smart_money_follow",
            description="Follows trusted smart-money wallets accumulating a token.",
            priority=15,
            ideal_regimes=(MarketRegime.BULL, MarketRegime.FOMO, MarketRegime.SIDEWAYS),
            forbidden_regimes=(MarketRegime.PANIC,),
            features_used=("wallet", "behavior", "security"),
            expected_holding_seconds=7200,
            historical_sharpe=1.6,
            profit_factor=1.8,
            win_rate=0.52,
            expectancy=0.4,
            lifecycle_stage=LifecycleStage.PRODUCTION,
        )

    def _evaluate(self, context: MarketContext) -> Evaluation:
        wallet = unit(context.member("wallet"))
        behavior = unit(context.member("behavior"))
        smart = context.smart_money_count
        dumb = context.dumb_money_count
        crowd = clamp01((smart - 0.5 * dumb) / 5.0) if smart else 0.0

        conviction = clamp01(0.5 * wallet + 0.2 * behavior + 0.3 * crowd)
        threshold = 0.55 / self.sensitivity
        drivers = (
            f"wallet trust {context.member('wallet'):.0f}/100",
            f"{smart} smart vs {dumb} dumb wallets",
        )
        if conviction >= threshold and smart >= 1:
            return Evaluation(
                signal_type=SignalType.BUY,
                score=conviction,
                headline="smart money accumulating",
                drivers=drivers,
                influencing=("wallet", "behavior", "smart_money_count", "dumb_money_count"),
                favorable=("trusted wallets buying", "few dumb-money holders"),
                risks=("smart money can distribute into strength",),
            )
        return Evaluation(
            signal_type=SignalType.IGNORE,
            score=conviction,
            headline="no clear smart-money accumulation",
            influencing=("wallet", "smart_money_count"),
            risks=("dumb money dominates",) if dumb > smart else (),
        )
