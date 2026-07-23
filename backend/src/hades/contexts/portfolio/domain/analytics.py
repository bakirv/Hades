"""Portfolio analytics - pure, dependency-free performance mathematics.

Everything here is a pure function over plain numbers: no NumPy, no I/O, no
state (the platform runs on low-power CPUs where NumPy 2 aborts, so the whole
codebase stays pure Python). These are the institutional performance and
risk statistics the spec asks for - Sharpe, Sortino, Calmar, Profit Factor,
Expectancy, Recovery Factor, Kelly Fraction and Risk of Ruin - each defined
conservatively and guarded against the degenerate inputs (empty series, zero
variance, no losses) that would otherwise divide by zero.

The functions are deliberately small and independently testable; the
:class:`PortfolioMetrics` value object bundles them into one snapshot via
:func:`compute_metrics`.
"""

from __future__ import annotations

import itertools
import math

from pydantic import Field

from hades.shared_kernel.domain.base import ValueObject

# A year of "periods" for annualising a per-trade Sharpe/Sortino. Meme-coin
# trades are short and frequent; 252 (trading days) is the conventional choice
# and keeps the numbers comparable to the rest of the industry.
_ANNUALISATION = 252.0


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: list[float], *, sample: bool = True) -> float:
    """Standard deviation. Sample (n-1) by default; 0 for <2 points."""
    n = len(xs)
    if n < 2:
        return 0.0
    mu = _mean(xs)
    var = sum((x - mu) ** 2 for x in xs) / (n - 1 if sample else n)
    return math.sqrt(max(0.0, var))


def sharpe_ratio(returns: list[float], *, risk_free: float = 0.0, annualise: bool = True) -> float:
    """Reward per unit of total volatility. 0 when there is no dispersion."""
    if len(returns) < 2:
        return 0.0
    excess = [r - risk_free for r in returns]
    sd = _std(excess)
    if sd == 0.0:
        return 0.0
    ratio = _mean(excess) / sd
    return round(ratio * (math.sqrt(_ANNUALISATION) if annualise else 1.0), 4)


def sortino_ratio(returns: list[float], *, risk_free: float = 0.0, annualise: bool = True) -> float:
    """Like Sharpe but penalises only downside deviation.

    When there is no downside (no return below the target) the ratio is
    undefined; we report 0.0 rather than infinity to stay comparable.
    """
    if len(returns) < 2:
        return 0.0
    excess = [r - risk_free for r in returns]
    downside = [min(0.0, e) for e in excess]
    dd = math.sqrt(sum(d * d for d in downside) / len(downside))
    if dd == 0.0:
        return 0.0
    ratio = _mean(excess) / dd
    return round(ratio * (math.sqrt(_ANNUALISATION) if annualise else 1.0), 4)


def max_drawdown(equity_curve: list[float]) -> float:
    """Largest peak-to-trough decline of an equity series, as a fraction [0, 1]."""
    peak = -math.inf
    worst = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak > 0:
            worst = max(worst, (peak - value) / peak)
    return round(worst, 6)


def calmar_ratio(roi: float, max_dd: float) -> float:
    """Return over maximum drawdown. 0 when there has been no drawdown."""
    if max_dd <= 0.0:
        return 0.0
    return round(roi / max_dd, 4)


def profit_factor(gross_win: float, gross_loss: float) -> float:
    """Gross profit divided by gross loss (``gross_loss`` given as a positive).

    Infinite when there are no losses; we cap it at a large finite sentinel so
    it stays JSON-serialisable and sortable.
    """
    if gross_loss <= 0.0:
        return 999.0 if gross_win > 0 else 0.0
    return round(gross_win / gross_loss, 4)


def expectancy(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """Expected profit per trade: p*avg_win - (1-p)*avg_loss (avg_loss positive)."""
    return round(win_rate * avg_win - (1.0 - win_rate) * abs(avg_loss), 6)


def recovery_factor(net_profit: float, max_dd_usd: float) -> float:
    """Net profit relative to the deepest capital loss suffered to earn it."""
    if max_dd_usd <= 0.0:
        return 0.0
    return round(net_profit / max_dd_usd, 4)


def kelly_fraction(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """The Kelly-optimal fraction of capital to risk, clipped to [0, 1].

    ``f* = p - (1-p)/b`` where ``b`` is the win/loss ratio. Negative Kelly (no
    edge) clips to 0 - never bet when the expectation is against you.
    """
    if avg_loss <= 0.0 or avg_win <= 0.0:
        return 0.0
    b = avg_win / abs(avg_loss)
    f = win_rate - (1.0 - win_rate) / b
    return round(min(1.0, max(0.0, f)), 4)


def risk_of_ruin(win_rate: float, risk_per_trade: float, *, ruin_fraction: float = 1.0) -> float:
    """Probability of losing ``ruin_fraction`` of capital, as a fraction [0, 1].

    Uses the classic gambler's-ruin approximation ``((1-e)/(1+e))^u`` where
    ``e`` is the per-trade edge and ``u`` the number of risk-units to ruin. With
    no edge ruin is certain (1.0); this is deliberately pessimistic.
    """
    edge = 2.0 * win_rate - 1.0
    if edge <= 0.0:
        return 1.0
    if risk_per_trade <= 0.0:
        return 0.0
    units = max(1.0, ruin_fraction / risk_per_trade)
    base = (1.0 - edge) / (1.0 + edge)
    probability = math.pow(base, units)
    return round(min(1.0, max(0.0, probability)), 6)


class PortfolioMetrics(ValueObject):
    """A full performance snapshot - every institutional statistic in one VO."""

    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    roi: float = 0.0
    net_profit_usd: float = 0.0
    avg_win_usd: float = 0.0
    avg_loss_usd: float = 0.0
    expectancy_usd: float = 0.0
    profit_factor: float = 0.0
    sharpe: float = 0.0
    sortino: float = 0.0
    calmar: float = 0.0
    max_drawdown_pct: float = 0.0
    recovery_factor: float = 0.0
    kelly_fraction: float = 0.0
    risk_of_ruin: float = 0.0
    extra: dict[str, float] = Field(default_factory=dict)


def compute_metrics(
    *,
    trade_pnls: list[float],
    equity_curve: list[float],
    starting_equity: float,
    risk_per_trade: float = 0.02,
) -> PortfolioMetrics:
    """Fold a trade-PnL series and an equity curve into a metrics snapshot.

    ``trade_pnls`` are realised per-trade profits/losses in USD (sign-carrying);
    ``equity_curve`` is the running equity used for drawdown and Sharpe. All
    edge cases (no trades, no losses, flat equity) resolve to conservative zeros.
    """
    total = len(trade_pnls)
    wins = [p for p in trade_pnls if p > 0]
    losses = [p for p in trade_pnls if p < 0]
    n_wins, n_losses = len(wins), len(losses)
    win_rate = n_wins / total if total else 0.0
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    net = sum(trade_pnls)
    avg_win = _mean(wins)
    avg_loss = abs(_mean(losses))

    # Period returns from the equity curve (fractional step-to-step change).
    returns: list[float] = []
    for prev, cur in itertools.pairwise(equity_curve):
        if prev > 0:
            returns.append((cur - prev) / prev)

    max_dd = max_drawdown(equity_curve)
    max_dd_usd = max_dd * (max(equity_curve) if equity_curve else starting_equity)
    roi = net / starting_equity if starting_equity > 0 else 0.0

    return PortfolioMetrics(
        total_trades=total,
        wins=n_wins,
        losses=n_losses,
        win_rate=round(win_rate, 4),
        roi=round(roi, 6),
        net_profit_usd=round(net, 6),
        avg_win_usd=round(avg_win, 6),
        avg_loss_usd=round(avg_loss, 6),
        expectancy_usd=expectancy(win_rate, avg_win, avg_loss),
        profit_factor=profit_factor(gross_win, gross_loss),
        sharpe=sharpe_ratio(returns),
        sortino=sortino_ratio(returns),
        calmar=calmar_ratio(roi, max_dd),
        max_drawdown_pct=round(max_dd * 100.0, 4),
        recovery_factor=recovery_factor(net, max_dd_usd),
        kelly_fraction=kelly_fraction(win_rate, avg_win, avg_loss),
        risk_of_ruin=risk_of_ruin(win_rate, risk_per_trade),
    )
