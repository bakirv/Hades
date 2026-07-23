"""The Risk Manager runs the full approval chain and is fully explainable.

These exercise the guardian end to end: a strong candidate is approved and sized,
each guard rejects with its own reason, the defence layer (kill switch, circuit
breaker, emergency) halts entries, and every decision emits an event + audit row.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hades.contexts.common.domain.value_objects import TokenMint, TokenRef
from hades.contexts.risk.application.factory import build_risk_manager
from hades.contexts.risk.domain.events import TradeApproved, TradeRejected
from hades.contexts.risk.domain.models import (
    CapitalSnapshot,
    CircuitBreakerReason,
    DrawdownSnapshot,
    ExposureLimits,
    OpenPositionView,
    PortfolioRiskState,
    RateLimits,
    RiskConfig,
    RiskDecision,
    RiskRejectReason,
    SizingConfig,
)
from hades.contexts.risk.infrastructure.stores import (
    InMemoryRiskAuditStore,
    InMemoryRiskStateStore,
)
from hades.shared_kernel.domain.events import DomainEvent
from hades.shared_kernel.events import InMemoryEventBus

_MINTS = [
    "So11111111111111111111111111111111111111112",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
]


def _token(i: int = 0) -> TokenRef:
    return TokenRef(mint=TokenMint(address=_MINTS[i]), symbol=f"T{i}")


def _candidate(**over: object):
    from hades.contexts.risk.domain.models import RiskCandidate

    base: dict[str, object] = {
        "token": _token(0),
        "at": datetime.now(UTC),
        "prob_roi_positive": 0.82,
        "prob_hit_tp": 0.7,
        "prob_hit_sl": 0.25,
        "confidence": 0.85,
        "security_score": 90.0,
        "developer_score": 80.0,
        "wallet_risk_score": 20.0,
        "liquidity_score": 85.0,
        "liquidity_usd": 50_000.0,
        "regime": "bull",
        "strategy": "momentum",
    }
    base.update(over)
    return RiskCandidate(**base)  # type: ignore[arg-type]


def _state(
    *,
    equity: float = 1000.0,
    positions: tuple[OpenPositionView, ...] = (),
    drawdown: DrawdownSnapshot | None = None,
) -> PortfolioRiskState:
    return PortfolioRiskState(
        capital=CapitalSnapshot(
            equity_usd=equity, cash_usd=equity, invested_usd=0.0, reserve_pct=0.0
        ),
        open_positions=positions,
        drawdown=drawdown or DrawdownSnapshot(peak_equity_usd=equity, current_equity_usd=equity),
    )


def _build(config: RiskConfig | None = None) -> tuple[object, InMemoryEventBus, list[DomainEvent]]:
    bus = InMemoryEventBus()
    events: list[DomainEvent] = []

    async def _capture(e: DomainEvent) -> None:
        events.append(e)

    bus.subscribe(TradeApproved.__name__, _capture)
    bus.subscribe(TradeRejected.__name__, _capture)
    manager = build_risk_manager(
        config or RiskConfig(),
        event_bus=bus,
        audit=InMemoryRiskAuditStore(),
        state_store=InMemoryRiskStateStore(),
    )
    return manager, bus, events


async def test_strong_candidate_is_approved_and_sized() -> None:
    manager, _bus, events = _build(RiskConfig(sizing=SizingConfig(max_position_size_usd=1000.0)))
    result = await manager.evaluate(_candidate(), _state())
    assert result.decision is RiskDecision.APPROVE
    assert result.sizing is not None
    assert float(result.sizing.notional.amount) > 0
    assert result.conviction > 0
    assert result.drivers  # explainability: at least one driver
    assert len(events) == 1 and isinstance(events[0], TradeApproved)


async def test_low_probability_rejected() -> None:
    manager, _bus, events = _build()
    result = await manager.evaluate(_candidate(prob_roi_positive=0.30), _state())
    assert result.decision is RiskDecision.REJECT
    assert result.reject_reason is RiskRejectReason.LOW_PROBABILITY
    assert result.blockers
    assert isinstance(events[0], TradeRejected)


async def test_low_security_rejected() -> None:
    manager, _bus, _events = _build()
    result = await manager.evaluate(_candidate(security_score=30.0), _state())
    assert result.reject_reason is RiskRejectReason.LOW_SECURITY_SCORE


async def test_security_veto_rejected() -> None:
    manager, _bus, _events = _build()
    result = await manager.evaluate(_candidate(security_approved=False), _state())
    assert result.reject_reason is RiskRejectReason.SECURITY_REJECTED


async def test_max_positions_rejected() -> None:
    manager, _bus, _events = _build(RiskConfig(rates=RateLimits(max_concurrent_positions=1)))
    positions = (OpenPositionView(token=_token(1), notional_usd=100.0),)
    result = await manager.evaluate(_candidate(), _state(positions=positions))
    assert result.reject_reason is RiskRejectReason.MAX_POSITIONS


async def test_no_deployable_capital_rejected() -> None:
    manager, _bus, _events = _build(
        RiskConfig(sizing=SizingConfig(min_position_size_usd=0.5, max_position_size_usd=1000.0))
    )
    # The whole balance is held as reserve -> nothing deployable, so the sizing
    # engine can only produce a below-minimum size and the trade is refused.
    state = PortfolioRiskState(
        capital=CapitalSnapshot(
            equity_usd=1000.0, cash_usd=1000.0, invested_usd=0.0, reserve_pct=100.0
        )
    )
    result = await manager.evaluate(_candidate(), state)
    assert result.reject_reason in (
        RiskRejectReason.INSUFFICIENT_CAPITAL,
        RiskRejectReason.POSITION_TOO_SMALL,
    )


async def test_portfolio_exposure_cap_rejected() -> None:
    manager, _bus, _events = _build(
        RiskConfig(
            sizing=SizingConfig(max_position_size_usd=1000.0),
            exposure=ExposureLimits(max_portfolio_pct=10.0),
        )
    )
    positions = (OpenPositionView(token=_token(1), notional_usd=90.0),)  # already 9%
    result = await manager.evaluate(_candidate(), _state(positions=positions))
    assert result.reject_reason in (
        RiskRejectReason.PORTFOLIO_EXPOSURE,
        RiskRejectReason.TOKEN_EXPOSURE,
    )


async def test_correlation_cap_rejected() -> None:
    manager, _bus, _events = _build(RiskConfig(rates=RateLimits(max_correlated_positions=1)))
    positions = (OpenPositionView(token=_token(1), notional_usd=50.0, developer="devX"),)
    result = await manager.evaluate(_candidate(developer="devX"), _state(positions=positions))
    assert result.reject_reason is RiskRejectReason.CORRELATED_POSITIONS


async def test_emergency_mode_blocks_everything() -> None:
    manager, _bus, _events = _build()
    await manager.enter_emergency("test")  # type: ignore[attr-defined]
    result = await manager.evaluate(_candidate(), _state())
    assert result.reject_reason is RiskRejectReason.EMERGENCY_MODE


async def test_circuit_breaker_blocks_everything() -> None:
    manager, _bus, _events = _build()
    await manager.trip_circuit_breaker(CircuitBreakerReason.MANUAL, "test")  # type: ignore[attr-defined]
    result = await manager.evaluate(_candidate(), _state())
    assert result.reject_reason is RiskRejectReason.CIRCUIT_BREAKER_OPEN


async def test_kill_switch_halts_after_drawdown() -> None:
    manager, _bus, _events = _build()
    # 25% drawdown -> PAPER_ONLY (blocks entries).
    dd = DrawdownSnapshot(peak_equity_usd=1000.0, current_equity_usd=750.0)
    result = await manager.evaluate(_candidate(), _state(drawdown=dd))
    assert result.reject_reason is RiskRejectReason.KILL_SWITCH_ENGAGED


async def test_record_losses_escalates_and_persists() -> None:
    store = InMemoryRiskStateStore()
    bus = InMemoryEventBus()
    manager = build_risk_manager(RiskConfig(), event_bus=bus, state_store=store)
    for _ in range(5):
        await manager.record_trade_result(is_win=False)
    control = await store.load()
    assert control is not None
    assert control.kill_switch.consecutive_losses == 5
    assert control.kill_switch.blocks_entries is True


@pytest.mark.parametrize("is_win", [True, False])
async def test_result_updates_streak(is_win: bool) -> None:
    manager = build_risk_manager(RiskConfig(), state_store=InMemoryRiskStateStore())
    await manager.record_trade_result(is_win=is_win)
    snap = manager.snapshot()
    assert snap.consecutive_losses == (0 if is_win else 1)
