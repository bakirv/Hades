"""The exit rules: when an open position should be closed.

These are the thresholds that used to exist only as sizing inputs — nothing read
them to actually close anything. Every boundary is pinned here, because an
off-by-one on a stop-loss is the difference between a bounded loss and an
unbounded one.
"""

from __future__ import annotations

from decimal import Decimal

from hades.contexts.execution.domain.exits import (
    EXIT_MAX_HOLD,
    EXIT_STOP_LOSS,
    EXIT_TAKE_PROFIT,
    EXIT_TRAILING,
    ExitPolicy,
    PositionMark,
    evaluate_exit,
)

_POLICY = ExitPolicy(
    take_profit_pct=40.0,
    stop_loss_pct=20.0,
    trailing_enabled=True,
    trailing_activation_pct=25.0,
    trailing_distance_pct=10.0,
)


def _mark(price: str, *, entry: str = "1.0", peak: str | None = None, held: float = 0.0):
    return PositionMark(
        entry_price=Decimal(entry),
        mark_price=Decimal(price),
        peak_price=Decimal(peak or max(price, entry, key=lambda v: Decimal(v))),
        held_seconds=held,
    )


# -- holding ---------------------------------------------------------------------


def test_a_position_inside_its_thresholds_is_held() -> None:
    assert evaluate_exit(_mark("1.10"), _POLICY) is None


def test_a_position_exactly_at_break_even_is_held() -> None:
    assert evaluate_exit(_mark("1.0"), _POLICY) is None


# -- take profit -----------------------------------------------------------------


def test_take_profit_fires_exactly_at_the_threshold() -> None:
    assert evaluate_exit(_mark("1.40"), _POLICY) == EXIT_TAKE_PROFIT


def test_take_profit_does_not_fire_one_tick_below() -> None:
    assert evaluate_exit(_mark("1.3999"), _POLICY) != EXIT_TAKE_PROFIT


def test_a_zero_take_profit_disables_the_rule_rather_than_firing_always() -> None:
    policy = ExitPolicy(take_profit_pct=0.0, stop_loss_pct=20.0, trailing_enabled=False)
    assert evaluate_exit(_mark("5.0"), policy) is None


# -- stop loss -------------------------------------------------------------------


def test_stop_loss_fires_exactly_at_the_threshold() -> None:
    assert evaluate_exit(_mark("0.80", peak="1.0"), _POLICY) == EXIT_STOP_LOSS


def test_stop_loss_does_not_fire_one_tick_above() -> None:
    assert evaluate_exit(_mark("0.8001", peak="1.0"), _POLICY) is None


def test_a_zero_stop_loss_disables_the_rule() -> None:
    policy = ExitPolicy(take_profit_pct=40.0, stop_loss_pct=0.0, trailing_enabled=False)
    assert evaluate_exit(_mark("0.01", peak="1.0"), policy) is None


def test_the_stop_wins_when_a_tick_gaps_through_both_thresholds() -> None:
    # A price that is somehow both below the stop and above the target is far
    # likelier to be a collapse than a windfall. Protect capital first.
    policy = ExitPolicy(take_profit_pct=1.0, stop_loss_pct=1.0, trailing_enabled=False)
    assert evaluate_exit(_mark("0.5", peak="2.0"), policy) == EXIT_STOP_LOSS


# -- trailing --------------------------------------------------------------------


def test_trailing_does_not_fire_before_it_is_armed() -> None:
    # Peak gain is only 20%, below the 25% activation — a 10% pullback from there
    # is ordinary noise, not an exit.
    assert evaluate_exit(_mark("1.08", peak="1.20"), _POLICY) is None


def test_trailing_fires_once_armed_and_the_pullback_is_reached() -> None:
    # Peak +50% arms it; 1.35 is exactly 10% below the 1.50 peak.
    assert evaluate_exit(_mark("1.35", peak="1.50"), _POLICY) == EXIT_TRAILING


def test_trailing_holds_while_the_pullback_is_shallower_than_the_distance() -> None:
    assert evaluate_exit(_mark("1.40", peak="1.50"), _POLICY) == EXIT_TAKE_PROFIT
    # Below the take-profit too, so only the trailing rule could fire — and does not.
    shallow = ExitPolicy(take_profit_pct=0.0, stop_loss_pct=20.0, trailing_enabled=True)
    assert evaluate_exit(_mark("1.45", peak="1.50"), shallow) is None


def test_trailing_can_be_switched_off() -> None:
    policy = ExitPolicy(take_profit_pct=0.0, stop_loss_pct=0.0, trailing_enabled=False)
    assert evaluate_exit(_mark("1.35", peak="1.50"), policy) is None


def test_trailing_protects_a_gain_the_take_profit_would_have_missed() -> None:
    # Ran to +50% without ever touching a 60% target, then gave back 10%.
    policy = ExitPolicy(take_profit_pct=60.0, stop_loss_pct=20.0, trailing_enabled=True)
    assert evaluate_exit(_mark("1.35", peak="1.50"), policy) == EXIT_TRAILING


# -- time stop -------------------------------------------------------------------


def test_the_time_stop_is_off_by_default() -> None:
    assert evaluate_exit(_mark("1.0", held=10_000.0), _POLICY) is None


def test_the_time_stop_fires_once_configured_and_reached() -> None:
    policy = ExitPolicy(take_profit_pct=40.0, stop_loss_pct=20.0, max_hold_seconds=60.0)
    assert evaluate_exit(_mark("1.0", held=60.0), policy) == EXIT_MAX_HOLD
    assert evaluate_exit(_mark("1.0", held=59.0), policy) is None


# -- degenerate input ------------------------------------------------------------


def test_an_unusable_price_is_never_a_sell_signal() -> None:
    # A broken feed must not be able to liquidate the book.
    assert evaluate_exit(_mark("0", peak="1.0"), _POLICY) is None
    assert evaluate_exit(_mark("1.0", entry="0", peak="1.0"), _POLICY) is None
