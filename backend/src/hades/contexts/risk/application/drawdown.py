"""Drawdown Engine - enforces rolling loss ceilings.

Losing control of drawdown is how quant books die. This engine reads the rolling
loss state (daily / weekly / monthly PnL and the daily stop-loss count) and
reports which, if any, ceiling has been breached. It is the input both to the
per-trade drawdown policy (block new entries when a window is blown) and to the
Kill Switch (which escalates its level on deep drawdown). Pure - it only reads a
:class:`DrawdownSnapshot` and compares against :class:`DrawdownLimits`.
"""

from __future__ import annotations

from hades.contexts.risk.domain.models import DrawdownLimits, DrawdownSnapshot


class DrawdownBreach:
    """A single breached loss ceiling."""

    __slots__ = ("limit_pct", "loss_pct", "window")

    def __init__(self, window: str, loss_pct: float, limit_pct: float) -> None:
        self.window = window
        self.loss_pct = loss_pct
        self.limit_pct = limit_pct


class DrawdownEngine:
    """Evaluates rolling loss windows against their configured ceilings."""

    def __init__(self, limits: DrawdownLimits) -> None:
        self._limits = limits

    def evaluate(self, dd: DrawdownSnapshot) -> DrawdownBreach | None:
        """Return the first (tightest-window) breached ceiling, or None.

        Daily is checked before weekly before monthly: the shortest window that
        is blown is the most urgent and the most specific cause to report.
        """
        # Absolute daily USD loss (independent of equity) is checked first.
        daily_loss_usd = -dd.daily_pnl_usd
        if (
            self._limits.daily_max_loss_usd > 0
            and daily_loss_usd >= self._limits.daily_max_loss_usd
        ):
            return DrawdownBreach(
                "daily_usd", round(daily_loss_usd, 2), self._limits.daily_max_loss_usd
            )
        if dd.daily_loss_pct >= self._limits.daily_pct:
            return DrawdownBreach("daily", dd.daily_loss_pct, self._limits.daily_pct)
        if dd.weekly_loss_pct >= self._limits.weekly_pct:
            return DrawdownBreach("weekly", dd.weekly_loss_pct, self._limits.weekly_pct)
        if dd.monthly_loss_pct >= self._limits.monthly_pct:
            return DrawdownBreach("monthly", dd.monthly_loss_pct, self._limits.monthly_pct)
        return None

    def stop_limit_breached(self, dd: DrawdownSnapshot) -> bool:
        """True when today's stop-loss count has hit its cap."""
        return dd.daily_stop_losses >= self._limits.daily_max_stop_losses
