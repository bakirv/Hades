"""Kill Switch - the graduated, self-escalating trading halt.

Five levels, exactly as the spec lays them out, each subsuming the ones below:

    1 REDUCED      3 consecutive losses  -> shrink new sizes (size_factor < 1)
    2 HALTED       5 consecutive losses  -> stop new entries for a cooldown
    3 OBSERVATION  daily drawdown blown   -> observe only, no entries
    4 PAPER_ONLY   critical drawdown      -> paper trading only
    5 EMERGENCY    catastrophic drawdown  -> stop everything, notify, audit

The switch is the one *stateful* risk component: it remembers the streak of
losses and the current level across evaluations (and, via the store, across
restarts). It never trades - it only raises or lowers the level and hands the
manager a ``size_factor`` and a ``blocks_entries`` flag. Transitions are pure
functions of (streak, drawdown, config); the class just holds the state and
emits the state object.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hades.contexts.risk.domain.models import (
    DrawdownSnapshot,
    KillSwitchConfig,
    KillSwitchLevel,
    KillSwitchState,
)


class KillSwitch:
    """Holds the current level + loss streak and re-derives the level on demand."""

    def __init__(self, config: KillSwitchConfig, state: KillSwitchState | None = None) -> None:
        self._cfg = config
        self._state = state or KillSwitchState()

    @property
    def state(self) -> KillSwitchState:
        return self._state

    def set_state(self, state: KillSwitchState) -> None:
        """Rehydrate from a persisted state (on startup)."""
        self._state = state

    # -- streak tracking ------------------------------------------------------

    def record_result(self, *, is_win: bool) -> KillSwitchState:
        """Update the consecutive-loss streak after a trade closes."""
        streak = 0 if is_win else self._state.consecutive_losses + 1
        self._state = self._state.model_copy(update={"consecutive_losses": streak})
        return self._reassess(self._state.consecutive_losses, drawdown_pct=None)

    def evaluate(self, dd: DrawdownSnapshot) -> KillSwitchState:
        """Re-derive the level from the current loss streak and drawdown."""
        return self._reassess(self._state.consecutive_losses, drawdown_pct=dd.drawdown_pct)

    def reset(self) -> KillSwitchState:
        """Clear the switch back to normal operation (human action)."""
        self._state = KillSwitchState()
        return self._state

    def trip(self, level: KillSwitchLevel, reason: str) -> KillSwitchState:
        """Force the switch to a level (manual escalation)."""
        self._state = self._build(level, reason, self._state.consecutive_losses)
        return self._state

    # -- level derivation -----------------------------------------------------

    def _reassess(self, streak: int, *, drawdown_pct: float | None) -> KillSwitchState:
        if not self._cfg.enabled:
            self._state = KillSwitchState(consecutive_losses=streak)
            return self._state

        level = KillSwitchLevel.NONE
        reason = ""

        # Drawdown-driven levels (3-5) - the deepest applicable wins.
        if drawdown_pct is not None:
            if drawdown_pct >= self._cfg.dd_emergency_pct:
                level, reason = KillSwitchLevel.EMERGENCY, f"drawdown {drawdown_pct:.1f}% critical"
            elif drawdown_pct >= self._cfg.dd_paper_only_pct:
                level, reason = KillSwitchLevel.PAPER_ONLY, f"drawdown {drawdown_pct:.1f}%"
            elif drawdown_pct >= self._cfg.dd_observation_pct:
                level, reason = KillSwitchLevel.OBSERVATION, f"drawdown {drawdown_pct:.1f}%"

        # Streak-driven levels (1-2) - only escalate, never downgrade a
        # drawdown-driven level already chosen above.
        if streak >= self._cfg.consecutive_losses_halt and level < KillSwitchLevel.HALTED:
            level, reason = KillSwitchLevel.HALTED, f"{streak} consecutive losses"
        elif streak >= self._cfg.consecutive_losses_reduce and level < KillSwitchLevel.REDUCED:
            level, reason = KillSwitchLevel.REDUCED, f"{streak} consecutive losses"

        self._state = self._build(level, reason, streak)
        return self._state

    def _build(self, level: KillSwitchLevel, reason: str, streak: int) -> KillSwitchState:
        now = datetime.now(UTC)
        size_factor = self._cfg.size_reduction_factor if level is KillSwitchLevel.REDUCED else 1.0
        if level.blocks_entries:
            size_factor = 0.0
        halted_until = (
            now + timedelta(minutes=self._cfg.halt_minutes)
            if level is KillSwitchLevel.HALTED
            else None
        )
        return KillSwitchState(
            level=level,
            reason=reason,
            consecutive_losses=streak,
            size_factor=size_factor,
            since=now if level is not KillSwitchLevel.NONE else None,
            halted_until=halted_until,
        )
