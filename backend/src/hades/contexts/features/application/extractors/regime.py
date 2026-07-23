"""Market-regime features — trend, acceleration, volatility state, dominance."""

from __future__ import annotations

from hades.contexts.features.application.extractors.base import price_series
from hades.contexts.features.application.indicators import slope, volatility
from hades.contexts.features.domain.models import FeatureInputs

_MICRO_WINDOW = 5
_EXPLOSION_RATIO = 2.0


class MarketRegimeFeatures:
    """Micro/macro trend, acceleration, vol compression/explosion, dominance."""

    @property
    def namespace(self) -> str:
        return "regime"

    def compute(self, inputs: FeatureInputs) -> dict[str, float]:
        prices = price_series(inputs)
        micro = slope(prices[-_MICRO_WINDOW:]) if len(prices) >= 2 else 0.0
        macro = slope(prices) if len(prices) >= 2 else 0.0
        acceleration = _acceleration(prices)
        recent_vol = volatility(prices[-10:])
        base_vol = volatility(prices)
        compression = recent_vol / base_vol if base_vol else 0.0
        buys, sells = self._flow(inputs)
        total_flow = buys + sells
        return {
            "micro_trend": micro,
            "macro_trend": macro,
            "acceleration": acceleration,
            "trend_alignment": 1.0 if micro * macro > 0 else 0.0,
            "volatility_recent": recent_vol,
            "volatility_base": base_vol,
            "volatility_compression": compression,
            "volatility_explosion": 1.0 if compression > _EXPLOSION_RATIO else 0.0,
            "buyer_dominance": buys / total_flow if total_flow else 0.5,
            "seller_dominance": sells / total_flow if total_flow else 0.5,
        }

    def _flow(self, inputs: FeatureInputs) -> tuple[float, float]:
        buys = float(inputs.buyers) + sum(p.buys for p in inputs.history)
        sells = float(inputs.sellers) + sum(p.sells for p in inputs.history)
        return buys, sells


def _acceleration(prices: list[float]) -> float:
    if len(prices) < 4:
        return 0.0
    mid = len(prices) // 2
    return slope(prices[mid:]) - slope(prices[:mid])
