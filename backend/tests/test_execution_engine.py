"""The Execution Engine orchestrates the flow and confines mode-awareness."""

from __future__ import annotations

from decimal import Decimal

from hades.contexts.common.domain.value_objects import (
    Money,
    Percentage,
    TokenMint,
    TokenRef,
)
from hades.contexts.execution.application.engine import ExecutionEngine
from hades.contexts.execution.application.order_manager import OrderManager
from hades.contexts.execution.application.transaction_manager import TransactionManager
from hades.contexts.execution.domain.events import OrderFailed, OrderFilled
from hades.contexts.execution.domain.models import (
    FillReport,
    OrderRequest,
    OrderSide,
    OrderStatus,
)
from hades.contexts.execution.domain.ports import Executor
from hades.contexts.notification.application.publisher import NotificationPublisher
from hades.contexts.portfolio.domain.events import PositionClosed, PositionOpened
from hades.contexts.risk.domain.events import TradeApproved
from hades.contexts.risk.domain.models import PositionSizing
from hades.shared_kernel.domain.events import DomainEvent
from hades.shared_kernel.domain.identifiers import new_id
from hades.shared_kernel.events import InMemoryEventBus

_MINT = "So11111111111111111111111111111111111111112"


def _token() -> TokenRef:
    return TokenRef(mint=TokenMint(address=_MINT), symbol="WSOL")


class _FakeExecutor:
    """A deterministic executor that records calls and reports a preset outcome."""

    def __init__(self, *, mode: str = "paper", fill: bool = True) -> None:
        self._mode = mode
        self._fill = fill
        self.calls: list[OrderRequest] = []

    @property
    def mode(self) -> str:
        return self._mode

    async def execute(self, request: OrderRequest) -> FillReport:
        self.calls.append(request)
        status = OrderStatus.FILLED if self._fill else OrderStatus.FAILED
        return FillReport(
            token=request.token,
            side=request.side,
            status=status,
            filled_quantity=Decimal(50) if self._fill else Decimal(0),
            average_price=Money(amount=Decimal(2)),
            fees=Money(amount=Decimal("0.25")),
            mode=self._mode,
            slippage_bps=100,
            notional=request.notional,
            error=None if self._fill else "simulated failure",
        )


def _engine(
    executors: dict[str, Executor], *, mode: str = "paper"
) -> tuple[ExecutionEngine, InMemoryEventBus, OrderManager]:
    bus = InMemoryEventBus()

    async def mode_provider() -> str:
        return mode

    om = OrderManager()
    engine = ExecutionEngine(
        executors=executors,
        mode_provider=mode_provider,
        order_manager=om,
        transaction_manager=TransactionManager(),
        event_bus=bus,
        notifier=NotificationPublisher(bus),
    )
    return engine, bus, om


def _capture(bus: InMemoryEventBus, name: str) -> list[DomainEvent]:
    events: list[DomainEvent] = []

    async def handler(event: DomainEvent) -> None:
        events.append(event)

    bus.subscribe(name, handler)
    return events


def _order(side: OrderSide = OrderSide.BUY) -> OrderRequest:
    return OrderRequest(
        token=_token(),
        side=side,
        notional=Money(amount=Decimal(100)),
        max_slippage_bps=300,
    )


def _approval() -> TradeApproved:
    sizing = PositionSizing(
        notional=Money(amount=Decimal(100)),
        take_profit=Percentage(value=40),
        stop_loss=Percentage(value=20),
        trailing_enabled=True,
        trailing_activation=Percentage(value=25),
        trailing_distance=Percentage(value=10),
    )
    return TradeApproved(
        aggregate_id=new_id(),
        token=_token(),
        sizing=sizing,
        conviction=0.8,
        risk_amount_usd=2.0,
        rationale="test approval",
        strategy="momentum",
        regime="trend",
    )


async def test_filled_buy_opens_a_position() -> None:
    paper = _FakeExecutor()
    engine, bus, om = _engine({"paper": paper})
    filled = _capture(bus, OrderFilled.__name__)
    opened = _capture(bus, PositionOpened.__name__)

    fill = await engine.execute(_order())

    assert fill.filled is True
    assert len(paper.calls) == 1
    assert len(filled) == 1
    assert len(opened) == 1
    pos = opened[0]
    assert isinstance(pos, PositionOpened)
    assert pos.tags == {}  # a bare order carries no attribution
    assert om.counts().get("filled") == 1


async def test_trade_approved_flows_through_to_a_position() -> None:
    paper = _FakeExecutor()
    engine, bus, _ = _engine({"paper": paper})
    opened = _capture(bus, PositionOpened.__name__)

    await engine.on_trade_approved(_approval())

    assert len(opened) == 1
    pos = opened[0]
    assert isinstance(pos, PositionOpened)
    # Risk attribution travels with the approval onto the opened position.
    assert pos.tags["strategy"] == "momentum"
    assert pos.tags["regime"] == "trend"


async def test_failed_order_emits_failure_and_no_position() -> None:
    engine, bus, om = _engine({"paper": _FakeExecutor(fill=False)})
    failed = _capture(bus, OrderFailed.__name__)
    opened = _capture(bus, PositionOpened.__name__)

    fill = await engine.execute(_order())

    assert fill.filled is False
    assert len(failed) == 1
    assert len(opened) == 0
    assert om.counts().get("failed") == 1


async def test_live_mode_without_a_live_executor_falls_back_to_paper() -> None:
    paper = _FakeExecutor(mode="paper")
    # Mode provider says "live", but only a paper executor is wired.
    engine, _bus, _ = _engine({"paper": paper}, mode="live")

    fill = await engine.execute(_order())

    # Fell back to paper — a config flag alone can never route to a live executor.
    assert fill.mode == "paper"
    assert len(paper.calls) == 1


async def test_live_executor_is_used_when_present_and_selected() -> None:
    paper = _FakeExecutor(mode="paper")
    live = _FakeExecutor(mode="live")
    engine, _bus, _ = _engine({"paper": paper, "live": live}, mode="live")

    fill = await engine.execute(_order())

    assert fill.mode == "live"
    assert len(live.calls) == 1
    assert len(paper.calls) == 0


async def test_sell_closes_the_position_opened_by_the_buy() -> None:
    engine, bus, _ = _engine({"paper": _FakeExecutor()})
    opened = _capture(bus, PositionOpened.__name__)
    closed = _capture(bus, PositionClosed.__name__)

    await engine.execute(_order(OrderSide.BUY))
    await engine.execute(_order(OrderSide.SELL))

    assert len(opened) == 1
    assert len(closed) == 1
    # The SELL closes the very position id the BUY opened.
    assert closed[0].aggregate_id == opened[0].aggregate_id
