"""Market Regime classifier — names the state of the market, never sizes it.

The spec asks for a model that classifies the market into one of several regimes
(bull, bear, sideways, highly volatile, low liquidity, panic, FOMO). It is a
*soft* classifier: it scores every regime and reports the winner plus the full
distribution and a confidence (how peaked that distribution is). Downstream, the
Risk Manager may widen/tighten its own thresholds per regime — the classifier
itself takes no action.

Transparent by construction: each regime's score is a small, documented, weighted
sum of normalised features. No opaque model.
"""

from __future__ import annotations

from hades.contexts.learning.application.mathx import clamp, entropy_norm
from hades.contexts.learning.domain.models import (
    MarketRegime,
    NormalizedVector,
    RegimeAssessment,
)


def _get(v: NormalizedVector, name: str, default: float = 0.0) -> float:
    return v.values.get(name, default)


class MarketRegimeClassifier:
    """Scores each market regime from the normalised feature vector."""

    def classify(self, vector: NormalizedVector) -> RegimeAssessment:
        if vector.coverage <= 0.0:
            return RegimeAssessment(detail="no features available")

        macro = _get(vector, "regime.macro_trend", 0.5)  # 0..1, 0.5 = flat
        micro = _get(vector, "regime.micro_trend", 0.5)
        slope = _get(vector, "tech.price_slope", 0.0)  # zscore-ish, may be <0
        align = _get(vector, "tech.trend_alignment", 0.5)
        vol = _get(vector, "tech.volatility", 0.2)  # 0..1 (clipped)
        vol_explosion = _get(vector, "tech.volatility_explosion", 0.0)
        liquidity = _get(vector, "basic.liquidity", 0.5)
        buyers = _get(vector, "basic.buyer_seller_ratio", 0.5)
        sellers = 1.0 - buyers
        trades = _get(vector, "basic.trades_5m", 0.3)
        holders_growth = _get(vector, "holders.holders_growth_pct", 0.5)

        up = (macro + micro + align) / 3.0
        down = 1.0 - up

        scores: dict[str, float] = {
            MarketRegime.BULL.value: clamp(0.55 * up + 0.25 * clamp(0.5 + slope) + 0.2 * buyers),
            MarketRegime.BEAR.value: clamp(0.55 * down + 0.25 * clamp(0.5 - slope) + 0.2 * sellers),
            MarketRegime.SIDEWAYS.value: clamp(
                0.6 * (1.0 - abs(up - 0.5) * 2.0) + 0.4 * (1.0 - vol)
            ),
            MarketRegime.HIGHLY_VOLATILE.value: clamp(0.6 * vol + 0.4 * vol_explosion),
            MarketRegime.LOW_LIQUIDITY.value: clamp(0.7 * (1.0 - liquidity) + 0.3 * (1.0 - trades)),
            MarketRegime.PANIC.value: clamp(0.4 * vol + 0.35 * sellers + 0.25 * clamp(0.5 - slope)),
            MarketRegime.FOMO.value: clamp(
                0.4 * buyers + 0.3 * trades + 0.3 * clamp(holders_growth)
            ),
        }

        winner = max(scores.items(), key=lambda kv: kv[1])
        # Confidence: how much the winner stands out from the field.
        confidence = clamp(winner[1] * (1.0 - entropy_norm(tuple(scores.values()))))
        confidence = clamp(confidence * (0.5 + 0.5 * vector.coverage))
        return RegimeAssessment(
            regime=MarketRegime(winner[0]),
            confidence=round(confidence, 4),
            scores={k: round(v, 4) for k, v in scores.items()},
            detail=self._detail(MarketRegime(winner[0])),
        )

    @staticmethod
    def _detail(regime: MarketRegime) -> str:
        return {
            MarketRegime.BULL: "trends up, buyers in control",
            MarketRegime.BEAR: "trends down, sellers in control",
            MarketRegime.SIDEWAYS: "range-bound, low directionality",
            MarketRegime.HIGHLY_VOLATILE: "large, erratic swings",
            MarketRegime.LOW_LIQUIDITY: "thin book, unreliable prints",
            MarketRegime.PANIC: "sharp downside under high volatility",
            MarketRegime.FOMO: "crowded buying, rapid holder growth",
            MarketRegime.UNKNOWN: "insufficient signal",
        }.get(regime, "")
