"""Performance metric computation — pure, dependency-free, deterministic.

Given a sequence of (virtual) trades the lab computes the full scorecard the rest
of the Research Lab ranks on. No single number is privileged: expectancy, profit
factor, Sharpe, Sortino, max drawdown, Calmar, recovery and consistency are all
computed together so a comparison can never be gamed by optimising ROI alone.

Everything here is pure Python and NumPy-free (the platform runs on low-power
CPUs where NumPy-2/SciPy abort), mirroring the AI Committee's ``mathx``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from hades.contexts.research.domain.models import (
    PerformanceMetrics,
    TradeRecord,
    safe_div,
)

_TRADING_PERIODS = 252.0  # annualisation factor for the Sharpe/Sortino ratios


def _mean(xs: Sequence[float]) -> float:
    return safe_div(sum(xs), len(xs))


def _std(xs: Sequence[float], *, ddof: int = 1) -> float:
    n = len(xs)
    if n <= ddof:
        return 0.0
    mu = _mean(xs)
    var = sum((x - mu) ** 2 for x in xs) / (n - ddof)
    return math.sqrt(max(var, 0.0))


def _downside_std(xs: Sequence[float], *, target: float = 0.0) -> float:
    downs = [min(x - target, 0.0) for x in xs]
    n = len(xs)
    if n <= 1:
        return 0.0
    var = sum(d * d for d in downs) / (n - 1)
    return math.sqrt(max(var, 0.0))


def equity_curve(returns: Sequence[float], *, start: float = 1.0) -> tuple[float, ...]:
    """Compound a return series into an equity curve (multiplicative)."""
    curve = [start]
    value = start
    for r in returns:
        value *= 1.0 + r
        curve.append(value)
    return tuple(curve)


def max_drawdown(curve: Sequence[float]) -> float:
    """Largest peak-to-trough decline of an equity curve, as a positive fraction."""
    peak = -math.inf
    worst = 0.0
    for v in curve:
        peak = max(peak, v)
        if peak > 0:
            worst = max(worst, (peak - v) / peak)
    return worst


def rolling_consistency(returns: Sequence[float], *, window: int = 10) -> float:
    """Fraction of rolling windows with a positive cumulative return (0..1)."""
    n = len(returns)
    if n == 0:
        return 0.0
    if n < window:
        return 1.0 if sum(returns) > 0 else 0.0
    positive = 0
    total = 0
    for i in range(n - window + 1):
        total += 1
        if sum(returns[i : i + window]) > 0:
            positive += 1
    return safe_div(positive, total)


def compute(trades: Sequence[TradeRecord]) -> PerformanceMetrics:
    """Compute the full scorecard from a sequence of trades."""
    if not trades:
        return PerformanceMetrics()

    returns = [t.ret for t in trades]
    n = len(returns)
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r < 0]
    gross_profit = sum(wins)
    gross_loss = -sum(losses)  # positive magnitude

    avg = _mean(returns)
    sd = _std(returns)
    dsd = _downside_std(returns)
    sharpe = safe_div(avg, sd) * math.sqrt(_TRADING_PERIODS) if sd else 0.0
    sortino = safe_div(avg, dsd) * math.sqrt(_TRADING_PERIODS) if dsd else 0.0

    curve = equity_curve(returns)
    mdd = max_drawdown(curve)
    total_return = curve[-1] - 1.0
    calmar = safe_div(total_return, mdd)
    recovery = safe_div(total_return, mdd)

    holding = [t.holding_seconds for t in trades if t.holding_seconds > 0]

    return PerformanceMetrics(
        trades=n,
        wins=len(wins),
        losses=len(losses),
        win_rate=round(safe_div(len(wins), n), 6),
        total_return=round(total_return, 6),
        avg_return=round(avg, 6),
        expectancy=round(avg, 6),
        profit_factor=round(safe_div(gross_profit, gross_loss, default=0.0), 6),
        sharpe=round(sharpe, 6),
        sortino=round(sortino, 6),
        max_drawdown=round(mdd, 6),
        calmar=round(calmar, 6),
        recovery_factor=round(recovery, 6),
        consistency=round(rolling_consistency(returns), 6),
        avg_holding=round(_mean(holding), 3) if holding else 0.0,
        gross_profit=round(gross_profit, 6),
        gross_loss=round(gross_loss, 6),
    )


def multi_objective_score(
    metrics: PerformanceMetrics,
    *,
    weights: dict[str, float] | None = None,
) -> float:
    """Blend the scorecard into one robustness-aware score for optimisation.

    ROI is deliberately *not* the whole objective: drawdown penalises and Sharpe,
    Sortino, profit factor and expectancy all contribute, so the optimiser cannot
    win by curve-fitting a fragile high-return path.
    """
    w = {
        "total_return": 1.0,
        "sharpe": 1.0,
        "sortino": 0.75,
        "profit_factor": 0.5,
        "expectancy": 1.0,
        "max_drawdown": 2.0,  # penalty weight
        **(weights or {}),
    }
    score = (
        w["total_return"] * metrics.total_return
        + w["sharpe"] * metrics.sharpe
        + w["sortino"] * metrics.sortino
        + w["profit_factor"] * metrics.profit_factor
        + w["expectancy"] * metrics.expectancy
        - w["max_drawdown"] * metrics.max_drawdown
    )
    # A strategy with too few trades is untrustworthy — shrink toward zero.
    support = min(1.0, metrics.trades / 30.0)
    return round(score * support, 6)
