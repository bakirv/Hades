"""Technical features — indicators over the price/volume/liquidity series.

Indicators are computed over several look-back periods, so a modest set of
formulas expands into a rich family of features for the models to learn from.
"""

from __future__ import annotations

from hades.contexts.features.application.extractors.base import price_series
from hades.contexts.features.application.indicators import (
    atr,
    ema,
    macd,
    momentum,
    roc,
    rsi,
    slope,
    sma,
    stddev,
    volatility,
    vwap,
)
from hades.contexts.features.domain.models import FeatureInputs

_MA_PERIODS = (5, 10, 20, 50)
_CHANGE_PERIODS = (5, 10)


class TechnicalFeatures:
    """EMA/SMA/VWAP/ATR/RSI/MACD/momentum/ROC/volatility/slopes."""

    @property
    def namespace(self) -> str:
        return "tech"

    def compute(self, inputs: FeatureInputs) -> dict[str, float]:
        prices = price_series(inputs)
        volumes = [p.volume for p in inputs.history]
        liquidities = [p.liquidity for p in inputs.history]
        features: dict[str, float] = {
            "vwap": vwap(prices, volumes) if len(volumes) == len(prices) else vwap(prices, []),
            "atr_14": atr(prices, 14),
            "rsi_14": rsi(prices, 14),
            "macd": macd(prices),
            "volatility": volatility(prices),
            "price_stddev": stddev(prices),
            "price_slope": slope(prices),
            "volume_slope": slope(volumes),
            "liquidity_slope": slope(liquidities),
            "volume_ma_5": sma(volumes, 5),
            "volume_ma_20": sma(volumes, 20),
            "series_length": float(len(prices)),
        }
        for period in _MA_PERIODS:
            features[f"sma_{period}"] = sma(prices, period)
            features[f"ema_{period}"] = ema(prices, period)
        for period in _CHANGE_PERIODS:
            features[f"momentum_{period}"] = momentum(prices, period)
            features[f"roc_{period}"] = roc(prices, period)
        return features
