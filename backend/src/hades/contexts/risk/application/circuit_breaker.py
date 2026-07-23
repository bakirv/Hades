"""Circuit Breaker - refuses to trade under unsafe operating conditions.

Distinct from the Kill Switch (which reacts to *losses*), the Circuit Breaker
reacts to *conditions that make trading itself unsafe*: an unstable RPC, extreme
latency, an illiquid market, a run of errors, or a failure of the AI, Security,
database, wallet or notification subsystems. When any is present the breaker is
open and no new trade is approved; when conditions clear (after a cooldown) it
closes again. It holds a small set of active reasons and an ``open_until`` time;
transitions are deterministic.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hades.contexts.risk.domain.models import (
    CircuitBreakerConfig,
    CircuitBreakerReason,
    CircuitBreakerState,
)


class CircuitBreaker:
    """Holds the open/closed posture and the reasons that opened it."""

    def __init__(
        self, config: CircuitBreakerConfig, state: CircuitBreakerState | None = None
    ) -> None:
        self._cfg = config
        self._state = state or CircuitBreakerState()
        self._error_streak = 0

    @property
    def state(self) -> CircuitBreakerState:
        return self._state

    def set_state(self, state: CircuitBreakerState) -> None:
        self._state = state

    def is_open(self) -> bool:
        """True while the breaker is open. Auto-closes once the cooldown lapses
        and no reason remains latched."""
        if not self._state.open:
            return False
        if self._state.open_until is not None and datetime.now(UTC) >= self._state.open_until:
            self.close("cooldown elapsed")
            return False
        return True

    def trip(self, reason: CircuitBreakerReason, detail: str = "") -> CircuitBreakerState:
        """Open the breaker for at least the configured cooldown."""
        if not self._cfg.enabled:
            return self._state
        now = datetime.now(UTC)
        reasons = tuple(sorted({*self._state.reasons, reason}))
        self._state = CircuitBreakerState(
            open=True,
            reasons=reasons,
            detail=detail or reason.value,
            since=self._state.since or now,
            open_until=now + timedelta(seconds=self._cfg.cooldown_seconds),
        )
        return self._state

    def close(self, detail: str = "") -> CircuitBreakerState:
        """Force the breaker closed (conditions recovered / manual)."""
        self._error_streak = 0
        self._state = CircuitBreakerState(open=False, detail=detail)
        return self._state

    # -- condition feeds ------------------------------------------------------

    def record_error(self, detail: str = "") -> CircuitBreakerState:
        """Feed a subsystem error; trips on a run of consecutive errors."""
        self._error_streak += 1
        if self._error_streak >= self._cfg.max_consecutive_errors:
            return self.trip(CircuitBreakerReason.REPEATED_ERRORS, detail or "error streak")
        return self._state

    def record_success(self) -> None:
        """Feed a healthy operation; resets the consecutive-error streak."""
        self._error_streak = 0

    def observe_latency(self, latency_ms: float) -> CircuitBreakerState:
        """Trip on extreme RPC latency."""
        if latency_ms >= self._cfg.max_rpc_latency_ms:
            return self.trip(CircuitBreakerReason.HIGH_LATENCY, f"latency {latency_ms:.0f}ms")
        return self._state
