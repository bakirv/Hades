"""The graduated Kill Switch and the Circuit Breaker transition correctly."""

from __future__ import annotations

from hades.contexts.risk.application.circuit_breaker import CircuitBreaker
from hades.contexts.risk.application.kill_switch import KillSwitch
from hades.contexts.risk.domain.models import (
    CircuitBreakerConfig,
    CircuitBreakerReason,
    DrawdownSnapshot,
    KillSwitchConfig,
    KillSwitchLevel,
)


def _ks() -> KillSwitch:
    return KillSwitch(
        KillSwitchConfig(
            consecutive_losses_reduce=3,
            consecutive_losses_halt=5,
            size_reduction_factor=0.5,
            dd_observation_pct=10.0,
            dd_paper_only_pct=20.0,
            dd_emergency_pct=30.0,
        )
    )


def test_three_losses_reduce_size() -> None:
    ks = _ks()
    for _ in range(3):
        state = ks.record_result(is_win=False)
    assert state.level is KillSwitchLevel.REDUCED
    assert state.size_factor == 0.5
    assert state.blocks_entries is False


def test_five_losses_halt_entries() -> None:
    ks = _ks()
    for _ in range(5):
        state = ks.record_result(is_win=False)
    assert state.level is KillSwitchLevel.HALTED
    assert state.blocks_entries is True
    assert state.size_factor == 0.0
    assert state.halted_until is not None


def test_a_win_resets_the_streak() -> None:
    ks = _ks()
    ks.record_result(is_win=False)
    ks.record_result(is_win=False)
    state = ks.record_result(is_win=True)
    assert state.consecutive_losses == 0
    assert state.level is KillSwitchLevel.NONE


def test_drawdown_drives_observation_then_paper_then_emergency() -> None:
    ks = _ks()
    assert ks.evaluate(DrawdownSnapshot(peak_equity_usd=100, current_equity_usd=88)).level is (
        KillSwitchLevel.OBSERVATION
    )
    assert ks.evaluate(DrawdownSnapshot(peak_equity_usd=100, current_equity_usd=75)).level is (
        KillSwitchLevel.PAPER_ONLY
    )
    assert ks.evaluate(DrawdownSnapshot(peak_equity_usd=100, current_equity_usd=65)).level is (
        KillSwitchLevel.EMERGENCY
    )


def test_deepest_condition_wins() -> None:
    ks = _ks()
    # 3 losses would be REDUCED, but a 25% drawdown is PAPER_ONLY - the stricter.
    ks.record_result(is_win=False)
    ks.record_result(is_win=False)
    ks.record_result(is_win=False)
    state = ks.evaluate(DrawdownSnapshot(peak_equity_usd=100, current_equity_usd=75))
    assert state.level is KillSwitchLevel.PAPER_ONLY


def test_reset_clears_everything() -> None:
    ks = _ks()
    for _ in range(5):
        ks.record_result(is_win=False)
    state = ks.reset()
    assert state.level is KillSwitchLevel.NONE
    assert state.consecutive_losses == 0


def test_disabled_kill_switch_never_engages() -> None:
    ks = KillSwitch(KillSwitchConfig(enabled=False, consecutive_losses_reduce=1))
    state = ks.record_result(is_win=False)
    assert state.level is KillSwitchLevel.NONE


# -- circuit breaker -----------------------------------------------------------


def _cb() -> CircuitBreaker:
    return CircuitBreaker(CircuitBreakerConfig(max_consecutive_errors=3, max_rpc_latency_ms=3000))


def test_error_streak_trips_breaker() -> None:
    cb = _cb()
    cb.record_error("rpc")
    cb.record_error("rpc")
    assert cb.is_open() is False
    cb.record_error("rpc")  # third -> trips
    assert cb.is_open() is True
    assert CircuitBreakerReason.REPEATED_ERRORS in cb.state.reasons


def test_success_resets_error_streak() -> None:
    cb = _cb()
    cb.record_error("x")
    cb.record_error("x")
    cb.record_success()
    cb.record_error("x")
    assert cb.is_open() is False  # streak was reset before the third


def test_high_latency_trips() -> None:
    cb = _cb()
    cb.observe_latency(5000)
    assert cb.is_open() is True
    assert CircuitBreakerReason.HIGH_LATENCY in cb.state.reasons


def test_manual_close() -> None:
    cb = _cb()
    cb.trip(CircuitBreakerReason.MANUAL, "test")
    assert cb.is_open() is True
    cb.close("recovered")
    assert cb.is_open() is False


def test_disabled_breaker_never_opens() -> None:
    cb = CircuitBreaker(CircuitBreakerConfig(enabled=False, max_consecutive_errors=1))
    cb.record_error("x")
    assert cb.is_open() is False
