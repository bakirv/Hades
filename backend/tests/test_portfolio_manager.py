"""The Portfolio Manager keeps the book honest from the Position event stream."""

from __future__ import annotations

from decimal import Decimal

from hades.contexts.common.domain.value_objects import Money, TokenMint, TokenRef
from hades.contexts.portfolio.application.portfolio_manager import PortfolioManager
from hades.contexts.portfolio.domain.events import (
    PositionClosed,
    PositionOpened,
    PositionUpdated,
)
from hades.shared_kernel.domain.identifiers import new_id
from hades.shared_kernel.events import InMemoryEventBus

_MINT = "So11111111111111111111111111111111111111112"


def _token() -> TokenRef:
    return TokenRef(mint=TokenMint(address=_MINT), symbol="WSOL")


def _manager() -> tuple[PortfolioManager, InMemoryEventBus]:
    bus = InMemoryEventBus()
    pm = PortfolioManager(starting_balance_usd=1000.0, reserve_pct=35.0, event_bus=bus)
    pm.register(bus)
    return pm, bus


async def test_open_reduces_cash_and_holds_invested() -> None:
    pm, bus = _manager()
    pid = new_id()
    await bus.publish(
        PositionOpened(
            aggregate_id=pid,
            token=_token(),
            entry_price=Money(amount="1"),
            quantity=Decimal(100),
            notional=Money(amount="100"),
            tags={"strategy": "momentum", "developer": "devX"},
        )
    )
    st = pm.state()
    assert st.cash_usd == 900.0
    assert st.invested_usd == 100.0
    assert st.equity_usd == 1000.0  # unchanged until marked
    assert st.open_positions == 1


async def test_mark_updates_unrealized_and_equity() -> None:
    pm, bus = _manager()
    pid = new_id()
    await bus.publish(
        PositionOpened(
            aggregate_id=pid,
            token=_token(),
            entry_price=Money(amount="1"),
            quantity=Decimal(100),
            notional=Money(amount="100"),
        )
    )
    await bus.publish(
        PositionUpdated(
            aggregate_id=pid, mark_price=Money(amount="1.5"), unrealized_pnl=Money(amount="50")
        )
    )
    st = pm.state()
    assert st.unrealized_pnl_usd == 50.0
    assert st.equity_usd == 1050.0


async def test_close_realizes_pnl_and_frees_capital() -> None:
    pm, bus = _manager()
    pid = new_id()
    await bus.publish(
        PositionOpened(
            aggregate_id=pid,
            token=_token(),
            entry_price=Money(amount="1"),
            quantity=Decimal(100),
            notional=Money(amount="100"),
            tags={"strategy": "momentum"},
        )
    )
    await bus.publish(
        PositionClosed(
            aggregate_id=pid,
            exit_price=Money(amount="1.4"),
            realized_pnl=Money(amount="40"),
            reason="take_profit",
        )
    )
    st = pm.state()
    assert st.open_positions == 0
    assert st.invested_usd == 0.0
    assert st.realized_pnl_usd == 40.0
    assert st.cash_usd == 1040.0  # 900 principal-out + 100 back + 40 profit
    assert pm.closed_trades()[0].pnl_usd == 40.0


async def test_risk_state_exposes_capital_and_tags() -> None:
    pm, bus = _manager()
    await bus.publish(
        PositionOpened(
            aggregate_id=new_id(),
            token=_token(),
            entry_price=Money(amount="1"),
            quantity=Decimal(100),
            notional=Money(amount="200"),
            tags={"strategy": "swing", "developer": "devY", "regime": "bull"},
        )
    )
    state = await pm.risk_state()
    assert state.open_count == 1
    assert state.open_positions[0].developer == "devY"
    assert state.open_positions[0].strategy == "swing"
    # Reserve of 35% on 1000 equity -> 350 held back; cash is 800 -> available 450.
    assert state.capital.reserve_usd == 350.0
    assert state.capital.available_usd == 450.0


async def test_consecutive_losses_from_closed_trades() -> None:
    pm, bus = _manager()
    for pnl in ("10", "-5", "-8"):
        pid = new_id()
        await bus.publish(
            PositionOpened(
                aggregate_id=pid,
                token=_token(),
                entry_price=Money(amount="1"),
                quantity=Decimal(1),
                notional=Money(amount="10"),
            )
        )
        await bus.publish(
            PositionClosed(
                aggregate_id=pid,
                exit_price=Money(amount="1"),
                realized_pnl=Money(amount=pnl),
                reason="manual",
            )
        )
    state = await pm.risk_state()
    assert state.consecutive_losses == 2  # last two were losses
