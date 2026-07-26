"""When an open position should be closed — the exit rules, as pure functions.

A position that can only be opened is not a strategy, it is a way to run out of
cash. Entry is decided by the Committee and the Risk Manager; *exit* is decided
here, by comparing the current mark against the entry and the peak.

The rules are deliberately kept as a total function over a
:class:`PositionMark` — no clock, no I/O, no event bus — so every boundary
(exactly at the take-profit, one basis point below the stop, trailing armed but
not yet breached) is unit-testable without a stack behind it. The loop that
fetches prices and places the sell lives in
:mod:`hades.contexts.execution.application.position_monitor`.

Precedence is not arbitrary. It runs **stop-loss → trailing → take-profit →
max-hold**, because when two rules fire on the same tick the one that protects
capital must win. A tick that gaps through both the stop and the target is far
likelier to be a collapse than a windfall, and taking the stop in that case is
the conservative reading.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

#: Exit reasons. These travel on ``PositionClosed.reason`` and are what the Risk
#: Manager counts as daily stop-losses, so they are part of the contract between
#: this module and the risk policies — not free-form labels.
EXIT_STOP_LOSS = "stop_loss"
EXIT_TRAILING = "trailing"
EXIT_TAKE_PROFIT = "take_profit"
EXIT_MAX_HOLD = "max_hold"


@dataclass(frozen=True)
class ExitPolicy:
    """The thresholds an open position is judged against.

    Percentages are of the entry price. ``max_hold_seconds`` of 0 disables the
    time stop; a negative or zero take-profit/stop-loss disables that rule rather
    than firing on every tick — a misconfigured threshold must not become an
    instant liquidation.
    """

    take_profit_pct: float = 40.0
    stop_loss_pct: float = 20.0
    trailing_enabled: bool = True
    trailing_activation_pct: float = 25.0
    trailing_distance_pct: float = 10.0
    max_hold_seconds: float = 0.0


@dataclass(frozen=True)
class PositionMark:
    """One position priced at a moment in time.

    ``peak_price`` is the highest mark seen since the position opened (never
    below the entry), which is what arms and then trails the stop.
    """

    entry_price: Decimal
    mark_price: Decimal
    peak_price: Decimal
    held_seconds: float = 0.0

    @property
    def roi_pct(self) -> float:
        """Price return since entry, in percent. Zero when the entry is unusable."""
        if self.entry_price <= 0:
            return 0.0
        return float((self.mark_price - self.entry_price) / self.entry_price) * 100.0

    @property
    def peak_roi_pct(self) -> float:
        """The best price return this position ever showed."""
        if self.entry_price <= 0:
            return 0.0
        return float((self.peak_price - self.entry_price) / self.entry_price) * 100.0

    @property
    def drawdown_from_peak_pct(self) -> float:
        """How far the mark has fallen from its peak, in percent of the peak."""
        if self.peak_price <= 0:
            return 0.0
        return float((self.peak_price - self.mark_price) / self.peak_price) * 100.0


def evaluate_exit(mark: PositionMark, policy: ExitPolicy) -> str | None:
    """Return the exit reason for this mark, or ``None`` to keep holding.

    Total and side-effect free: the caller decides what to do with the answer.
    """
    if mark.entry_price <= 0 or mark.mark_price <= 0:
        # An unusable price is not a sell signal. Refusing to act on it is the
        # safe reading: a bad feed must never liquidate the book.
        return None

    roi = mark.roi_pct

    if policy.stop_loss_pct > 0 and roi <= -policy.stop_loss_pct:
        return EXIT_STOP_LOSS

    if (
        policy.trailing_enabled
        and policy.trailing_distance_pct > 0
        and mark.peak_roi_pct >= policy.trailing_activation_pct
        and mark.drawdown_from_peak_pct >= policy.trailing_distance_pct
    ):
        return EXIT_TRAILING

    if policy.take_profit_pct > 0 and roi >= policy.take_profit_pct:
        return EXIT_TAKE_PROFIT

    if policy.max_hold_seconds > 0 and mark.held_seconds >= policy.max_hold_seconds:
        return EXIT_MAX_HOLD

    return None


__all__ = [
    "EXIT_MAX_HOLD",
    "EXIT_STOP_LOSS",
    "EXIT_TAKE_PROFIT",
    "EXIT_TRAILING",
    "ExitPolicy",
    "PositionMark",
    "evaluate_exit",
]
