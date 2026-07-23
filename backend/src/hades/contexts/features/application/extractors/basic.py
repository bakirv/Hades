"""Basic features — raw magnitudes and simple growth/ratio derivations."""

from __future__ import annotations

from hades.contexts.features.application.indicators import slope
from hades.contexts.features.domain.models import FeatureInputs


class BasicFeatures:
    """Market-cap, liquidity, volume, trade counts and their growth rates."""

    @property
    def namespace(self) -> str:
        return "basic"

    def compute(self, inputs: FeatureInputs) -> dict[str, float]:
        age = (
            (inputs.now - inputs.created_at).total_seconds()
            if inputs.created_at is not None
            else 0.0
        )
        vol = inputs.volume
        features: dict[str, float] = {
            "age_seconds": max(0.0, age),
            "age_minutes": max(0.0, age / 60.0),
            "market_cap": inputs.market_cap,
            "fdv": inputs.fdv,
            "liquidity": inputs.liquidity,
            "tvl": inputs.tvl,
            "price": inputs.price,
            "spread_bps": inputs.spread_bps,
            "slippage_bps": inputs.slippage_bps,
            "volume": vol,
            "buy_volume": inputs.buy_volume,
            "sell_volume": inputs.sell_volume,
            "buyers": float(inputs.buyers),
            "sellers": float(inputs.sellers),
            "trades_1m": float(inputs.trades_1m),
            "trades_5m": float(inputs.trades_5m),
            "trades_15m": float(inputs.trades_15m),
            "trades_1h": float(inputs.trades_1h),
            "buy_sell_volume_ratio": _ratio(inputs.buy_volume, inputs.sell_volume),
            "buyer_seller_ratio": _ratio(inputs.buyers, inputs.sellers),
            "liquidity_to_mcap": _ratio(inputs.liquidity, inputs.market_cap),
            "volume_to_liquidity": _ratio(vol, inputs.liquidity),
        }
        features.update(self._growth(inputs))
        return features

    def _growth(self, inputs: FeatureInputs) -> dict[str, float]:
        volumes = [p.volume for p in inputs.history]
        liquidities = [p.liquidity for p in inputs.history]
        holders_growth = 0.0
        if inputs.holders is not None and inputs.holders.prev_count:
            holders_growth = (
                inputs.holders.count - inputs.holders.prev_count
            ) / inputs.holders.prev_count
        return {
            "volume_growth_slope": slope(volumes),
            "liquidity_growth_pct": _change(liquidities),
            "holders_growth_pct": holders_growth,
        }


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _change(series: list[float]) -> float:
    if len(series) < 2 or not series[0]:
        return 0.0
    return (series[-1] - series[0]) / series[0]
