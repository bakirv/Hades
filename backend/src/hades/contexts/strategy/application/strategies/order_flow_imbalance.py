"""Order Flow Imbalance - trades a lopsided buy/sell balance.

Persistent one-sided flow moves price. This strategy reads the microstructure
member together with an explicit order-flow-imbalance feature (buy volume minus
sell volume, normalised): a strong positive imbalance is a BUY, a strong negative
one an EXIT. Balanced flow is no signal.
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


class OrderFlowImbalanceStrategy(BaseStrategy):
    @classmethod
    def _describe(cls) -> StrategyMetadata:
        return StrategyMetadata(
            name="order_flow_imbalance",
            description="Trades persistent buy/sell order-flow imbalance.",
            priority=38,
            ideal_regimes=(MarketRegime.BULL, MarketRegime.FOMO, MarketRegime.HIGHLY_VOLATILE),
            forbidden_regimes=(MarketRegime.LOW_LIQUIDITY,),
            features_used=("microstructure", "order_flow_imbalance"),
            expected_holding_seconds=900,
            historical_sharpe=1.35,
            profit_factor=1.5,
            win_rate=0.5,
            expectancy=0.2,
            lifecycle_stage=LifecycleStage.PRODUCTION,
        )

    def _evaluate(self, context: MarketContext) -> Evaluation:
        # imbalance in [-1, 1]; fall back to a centred microstructure read.
        imbalance = context.feature(
            "order_flow_imbalance", (unit(context.member("microstructure")) - 0.5) * 2.0
        )
        microstructure = unit(context.member("microstructure"))
        threshold = 0.5 / self.sensitivity

        if imbalance > 0:
            conviction = clamp01(0.6 * imbalance + 0.4 * microstructure)
            if conviction >= threshold:
                return Evaluation(
                    signal_type=SignalType.BUY,
                    score=conviction,
                    headline="buy-side order-flow imbalance",
                    drivers=(f"imbalance {imbalance:+.2f}",),
                    influencing=("order_flow_imbalance", "microstructure"),
                    favorable=("persistent buying pressure",),
                    risks=("imbalance can flip on a single large seller",),
                )
        elif imbalance <= -0.4:
            conviction = clamp01(0.6 * (-imbalance) + 0.4 * (1.0 - microstructure))
            return Evaluation(
                signal_type=SignalType.EXIT,
                score=conviction,
                headline="sell-side order-flow imbalance",
                drivers=(f"imbalance {imbalance:+.2f}",),
                influencing=("order_flow_imbalance", "microstructure"),
                risks=("dominant selling pressure",),
            )
        return Evaluation(
            signal_type=SignalType.IGNORE,
            score=0.2,
            headline="order flow balanced",
            influencing=("order_flow_imbalance",),
        )
