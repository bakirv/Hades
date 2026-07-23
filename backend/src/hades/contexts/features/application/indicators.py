"""Pure technical-indicator functions over price/volume series.

Deliberately dependency-free (no numpy) so they run anywhere, including the
low-power VPS the platform targets. Every function is total: it returns a finite
float for any input, degrading gracefully (usually to ``0.0`` or the last value)
when the series is too short. All are trivially unit-testable.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from itertools import pairwise


def sma(values: Sequence[float], period: int) -> float:
    """Simple moving average of the last ``period`` values."""
    if not values or period <= 0:
        return 0.0
    window = values[-period:]
    return sum(window) / len(window)


def ema(values: Sequence[float], period: int) -> float:
    """Exponential moving average (seeded with the first value)."""
    if not values or period <= 0:
        return 0.0
    k = 2.0 / (period + 1.0)
    result = values[0]
    for v in values[1:]:
        result = v * k + result * (1.0 - k)
    return result


def stddev(values: Sequence[float]) -> float:
    """Population standard deviation."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    return math.sqrt(variance)


def returns(values: Sequence[float]) -> list[float]:
    """Simple period-over-period returns of a series."""
    out: list[float] = []
    for prev, cur in pairwise(values):
        out.append((cur - prev) / prev if prev else 0.0)
    return out


def volatility(values: Sequence[float]) -> float:
    """Standard deviation of returns (realised volatility)."""
    return stddev(returns(values))


def rsi(values: Sequence[float], period: int = 14) -> float:
    """Relative Strength Index in [0, 100]; 50 when undefined."""
    if len(values) <= period:
        return 50.0
    gains = 0.0
    losses = 0.0
    for prev, cur in pairwise(values[-period - 1 :]):
        delta = cur - prev
        if delta >= 0:
            gains += delta
        else:
            losses -= delta
    if losses == 0:
        return 100.0
    rs = (gains / period) / (losses / period)
    return 100.0 - (100.0 / (1.0 + rs))


def atr(values: Sequence[float], period: int = 14) -> float:
    """Average true range approximated from a close-only series."""
    if len(values) < 2:
        return 0.0
    trs = [abs(cur - prev) for prev, cur in pairwise(values)]
    window = trs[-period:]
    return sum(window) / len(window) if window else 0.0


def macd(values: Sequence[float], fast: int = 12, slow: int = 26) -> float:
    """MACD line = EMA(fast) - EMA(slow)."""
    return ema(values, fast) - ema(values, slow)


def roc(values: Sequence[float], period: int) -> float:
    """Rate of change over ``period`` steps, as a fraction."""
    if len(values) <= period:
        return 0.0
    past = values[-period - 1]
    return (values[-1] - past) / past if past else 0.0


def momentum(values: Sequence[float], period: int) -> float:
    """Absolute price change over ``period`` steps."""
    if len(values) <= period:
        return 0.0
    return values[-1] - values[-period - 1]


def vwap(prices: Sequence[float], volumes: Sequence[float]) -> float:
    """Volume-weighted average price (falls back to SMA when no volume)."""
    total_vol = sum(volumes)
    if total_vol <= 0:
        return sma(prices, len(prices)) if prices else 0.0
    return sum(p * v for p, v in zip(prices, volumes, strict=False)) / total_vol


def slope(values: Sequence[float]) -> float:
    """Least-squares slope of the series against its index (trend direction)."""
    n = len(values)
    if n < 2:
        return 0.0
    xs = range(n)
    mean_x = (n - 1) / 2.0
    mean_y = sum(values) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values, strict=False))
    den = sum((x - mean_x) ** 2 for x in xs)
    return num / den if den else 0.0
