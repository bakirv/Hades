"""The Position Monitor: the loop that makes an open position a live thing.

The regression these guard is the one an operator described as "the portfolio
page is decoration": positions opened, and then nothing ever re-priced them and
nothing ever sold them, so unrealised PnL, realised PnL and equity all sat
exactly where they started for the life of the process.
"""

from __future__ import annotations

from decimal import Decimal

from hades.contexts.common.domain.value_objects import Money, TokenMint, TokenRef
from hades.contexts.execution.application.position_monitor import PositionMonitor
from hades.contexts.execution.domain.exits import (
    EXIT_STOP_LOSS,
    EXIT_TAKE_PROFIT,
    ExitPolicy,
)
from hades.contexts.execution.domain.models import OrderRequest, OrderSide
from hades.contexts.execution.infrastructure.price_oracle import StaticPriceOracle
from hades.contexts.portfolio.domain.events import (
    PositionClosed,
    PositionOpened,
    PositionUpdated,
)
from hades.shared_kernel.domain.identifiers import new_id
from hades.shared_kernel.events.bus import InMemoryEventBus

_MINT = "So11111111111111111111111111111111111111112"

_POLICY = ExitPolicy(
    take_profit_pct=40.0,
    stop_loss_pct=20.0,
    trailing_enabled=True,
    trailing_activation_pct=25.0,
    trailing_distance_pct=10.0,
)


def _token() -> TokenRef:
    return TokenRef(mint=TokenMint(address=_MINT), symbol="WSOL")


class _RecordingEngine:
    """Stands in for the Execution Engine; records the orders it is handed."""

    def __init__(self, *, fail: bool = False) -> None:
        self.orders: list[OrderRequest] = []
        self.fail = fail

    async def execute(self, request: OrderRequest) -> None:
        self.orders.append(request)
        if self.fail:
            raise RuntimeError("executor unavailable")


def _capture(bus: InMemoryEventBus, event_type: str) -> list:
    captured: list = []

    async def handler(event: object) -> None:
        captured.append(event)

    bus.subscribe(event_type, handler)
    return captured


async def _monitor(
    *,
    price: str = "1.0",
    policy: ExitPolicy = _POLICY,
    engine: _RecordingEngine | None = None,
    oracle: object | None = None,
) -> tuple[PositionMonitor, _RecordingEngine, InMemoryEventBus]:
    bus = InMemoryEventBus()
    engine = engine or _RecordingEngine()
    monitor = PositionMonitor(
        engine=engine,  # type: ignore[arg-type]
        price_oracle=oracle or StaticPriceOracle({_MINT: Decimal(price)}),  # type: ignore[arg-type]
        event_bus=bus,
        policy=policy,
    )
    monitor.register(bus)
    return monitor, engine, bus


async def _open(bus: InMemoryEventBus, *, entry: str = "1.0", quantity: str = "100") -> str:
    position_id = str(new_id())
    await bus.publish(
        PositionOpened(
            aggregate_id=position_id,
            token=_token(),
            entry_price=Money(amount=Decimal(entry)),
            quantity=Decimal(quantity),
            notional=Money(amount=Decimal(entry) * Decimal(quantity)),
            tags={"strategy": "momentum"},
        )
    )
    return position_id


# -- tracking --------------------------------------------------------------------


async def test_an_opened_position_starts_being_tracked() -> None:
    monitor, _, bus = await _monitor()

    await _open(bus)

    assert len(monitor.tracked) == 1


async def test_a_closed_position_stops_being_tracked() -> None:
    monitor, _, bus = await _monitor()
    position_id = await _open(bus)

    await bus.publish(
        PositionClosed(
            aggregate_id=position_id,
            exit_price=Money(amount=Decimal(1)),
            realized_pnl=Money(amount=Decimal(0)),
            reason="manual",
        )
    )

    assert monitor.tracked == ()


# -- marking to market -----------------------------------------------------------


async def test_marking_publishes_the_unrealised_pnl_that_moves_the_portfolio() -> None:
    # THE regression: without this event the Portfolio Manager's unrealised PnL
    # stays at zero for the whole life of the position.
    monitor, _, bus = await _monitor(price="1.10")
    await _open(bus, entry="1.0", quantity="100")
    updates = _capture(bus, PositionUpdated.__name__)

    marked = await monitor.tick()

    assert marked == 1
    assert len(updates) == 1
    assert updates[0].mark_price.amount == Decimal("1.10")
    # 100 tokens that rose from 1.00 to 1.10 → +10 USD unrealised.
    assert updates[0].unrealized_pnl.amount == Decimal("10.00")


async def test_a_losing_position_marks_a_negative_unrealised_pnl() -> None:
    monitor, _, bus = await _monitor(price="0.90")
    await _open(bus, entry="1.0", quantity="100")
    updates = _capture(bus, PositionUpdated.__name__)

    await monitor.tick()

    assert updates[0].unrealized_pnl.amount == Decimal("-10.00")


async def test_an_unpriceable_position_is_held_not_marked() -> None:
    # A broken feed must never mark the book at an invented number.
    monitor, engine, bus = await _monitor(oracle=StaticPriceOracle({}))
    await _open(bus)
    updates = _capture(bus, PositionUpdated.__name__)

    marked = await monitor.tick()

    assert marked == 0
    assert updates == []
    assert engine.orders == []
    assert len(monitor.tracked) == 1


async def test_an_oracle_that_raises_does_not_break_the_tick() -> None:
    class _Broken:
        async def price_usd(self, token: TokenRef) -> Decimal:
            raise RuntimeError("feed down")

    monitor, _, bus = await _monitor(oracle=_Broken())
    await _open(bus)

    assert await monitor.tick() == 0
    assert len(monitor.tracked) == 1


# -- exits ------------------------------------------------------------------------


async def test_hitting_the_take_profit_places_a_sell_through_the_engine() -> None:
    monitor, engine, bus = await _monitor(price="1.50")
    await _open(bus, entry="1.0", quantity="100")

    await monitor.tick()

    assert len(engine.orders) == 1
    order = engine.orders[0]
    assert order.side is OrderSide.SELL
    assert order.tags["exit_reason"] == EXIT_TAKE_PROFIT
    # The sell is sized at the position's market value: 100 tokens at 1.50.
    assert order.notional.amount == Decimal("150.00")


async def test_hitting_the_stop_loss_places_a_sell() -> None:
    monitor, engine, bus = await _monitor(price="0.75")
    await _open(bus, entry="1.0", quantity="100")

    await monitor.tick()

    assert engine.orders[0].tags["exit_reason"] == EXIT_STOP_LOSS


async def test_the_exit_keeps_the_risk_attribution_of_the_position() -> None:
    monitor, engine, bus = await _monitor(price="1.50")
    await _open(bus)

    await monitor.tick()

    assert engine.orders[0].tags["strategy"] == "momentum"
    assert engine.orders[0].strategy == "momentum"


async def test_a_position_inside_its_thresholds_is_marked_but_not_sold() -> None:
    monitor, engine, bus = await _monitor(price="1.10")
    await _open(bus)

    await monitor.tick()

    assert engine.orders == []


async def test_a_position_is_never_sold_twice_while_its_exit_is_in_flight() -> None:
    # The engine here never publishes PositionClosed, so the position stays
    # tracked — exactly the situation in which a second sell would be issued.
    monitor, engine, bus = await _monitor(price="1.50")
    await _open(bus)

    await monitor.tick()
    await monitor.tick()
    await monitor.tick()

    assert len(engine.orders) == 1


async def test_a_failed_exit_is_retried_on_the_next_tick() -> None:
    # A position stuck in "exiting" after a failed sell would never be closed
    # by anything at all.
    monitor, engine, bus = await _monitor(price="1.50", engine=_RecordingEngine(fail=True))
    await _open(bus)

    await monitor.tick()
    await monitor.tick()

    assert len(engine.orders) == 2


async def test_the_trailing_stop_uses_the_peak_seen_across_ticks() -> None:
    # Runs to +30% (arming the 25% trailing), then gives back more than 10%.
    bus = InMemoryEventBus()
    engine = _RecordingEngine()
    oracle = StaticPriceOracle({_MINT: Decimal("1.30")})
    monitor = PositionMonitor(
        engine=engine,  # type: ignore[arg-type]
        price_oracle=oracle,  # type: ignore[arg-type]
        event_bus=bus,
        policy=ExitPolicy(
            take_profit_pct=0.0,  # isolate the trailing rule
            stop_loss_pct=0.0,
            trailing_enabled=True,
            trailing_activation_pct=25.0,
            trailing_distance_pct=10.0,
        ),
    )
    monitor.register(bus)
    await _open(bus, entry="1.0", quantity="100")

    await monitor.tick()  # peak set to 1.30, no exit
    assert engine.orders == []

    oracle.set(_MINT, Decimal("1.15"))  # ~11.5% below the peak
    await monitor.tick()

    assert len(engine.orders) == 1
    assert engine.orders[0].tags["exit_reason"] == "trailing"
