"""Portfolio analytics are correct and guard every degenerate input."""

from __future__ import annotations

from hades.contexts.portfolio.domain.analytics import (
    calmar_ratio,
    compute_metrics,
    expectancy,
    kelly_fraction,
    max_drawdown,
    profit_factor,
    risk_of_ruin,
    sharpe_ratio,
    sortino_ratio,
)


def test_max_drawdown_peak_to_trough() -> None:
    curve = [100.0, 120.0, 90.0, 110.0]
    # Peak 120 -> trough 90 == 25% drawdown.
    assert max_drawdown(curve) == 0.25


def test_max_drawdown_monotonic_up_is_zero() -> None:
    assert max_drawdown([10.0, 20.0, 30.0]) == 0.0


def test_sharpe_zero_when_no_dispersion() -> None:
    assert sharpe_ratio([0.01, 0.01, 0.01]) == 0.0


def test_sharpe_positive_for_positive_mean() -> None:
    assert sharpe_ratio([0.01, 0.02, 0.015, 0.03]) > 0


def test_sortino_ignores_upside_volatility() -> None:
    # No downside deviation -> defined as 0 (not infinity).
    assert sortino_ratio([0.01, 0.02, 0.03]) == 0.0


def test_profit_factor_no_losses_capped() -> None:
    assert profit_factor(100.0, 0.0) == 999.0
    assert profit_factor(0.0, 0.0) == 0.0


def test_profit_factor_ratio() -> None:
    assert profit_factor(200.0, 100.0) == 2.0


def test_calmar_zero_without_drawdown() -> None:
    assert calmar_ratio(0.5, 0.0) == 0.0
    assert calmar_ratio(0.5, 0.25) == 2.0


def test_expectancy_sign() -> None:
    # 60% win rate, +10 avg win, -5 avg loss -> positive expectancy.
    assert expectancy(0.6, 10.0, 5.0) > 0
    # 40% win rate against a bigger loss -> negative expectancy.
    assert expectancy(0.4, 5.0, 10.0) < 0


def test_kelly_clips_no_edge_to_zero() -> None:
    assert kelly_fraction(0.3, 1.0, 1.0) == 0.0  # losing edge -> 0
    assert 0.0 < kelly_fraction(0.6, 2.0, 1.0) <= 1.0


def test_risk_of_ruin_certain_without_edge() -> None:
    assert risk_of_ruin(0.5, 0.02) == 1.0  # no edge -> ruin certain
    assert risk_of_ruin(0.7, 0.02) < 1.0  # real edge -> survivable


def test_compute_metrics_full_snapshot() -> None:
    pnls = [10.0, -5.0, 20.0, -8.0, 15.0]
    curve = [1000.0, 1010.0, 1005.0, 1025.0, 1017.0, 1032.0]
    m = compute_metrics(trade_pnls=pnls, equity_curve=curve, starting_equity=1000.0)
    assert m.total_trades == 5
    assert m.wins == 3
    assert m.losses == 2
    assert m.win_rate == 0.6
    assert m.net_profit_usd == 32.0
    assert m.profit_factor > 1.0  # net winner
    assert m.max_drawdown_pct >= 0.0


def test_compute_metrics_empty_is_safe() -> None:
    m = compute_metrics(trade_pnls=[], equity_curve=[1000.0], starting_equity=1000.0)
    assert m.total_trades == 0
    assert m.profit_factor == 0.0
    assert m.sharpe == 0.0
    assert m.risk_of_ruin in (0.0, 1.0)
