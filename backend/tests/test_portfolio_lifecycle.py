"""The whole loop: buy → mark → exit → realised PnL, with the real components.

This is the end-to-end version of the bug an operator reported as "the portfolio
page is decoration". The platform could open a position and nothing else: no
component re-priced what was held, and no component ever issued a SELL. The
observable result was a book whose equity, unrealised PnL, realised PnL and
equity curve were all frozen from the moment the process started.

Everything here is the production wiring — the real Portfolio Manager, the real
Execution Engine, the real Paper Executor and the real Position Monitor, joined
by the real event bus. Only the price feed is a stand-in, because the assertions
are about what the book does when a price moves.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

from hades.contexts.common.domain.value_objects import Money, TokenMint, TokenRef
from hades.contexts.execution.application.engine import ExecutionEngine
from hades.contexts.execution.application.fees import FeeEngine
from hades.contexts.execution.application.order_manager import OrderManager
from hades.contexts.execution.application.paper_executor import PaperExecutor
from hades.contexts.execution.application.position_monitor import PositionMonitor
from hades.contexts.execution.application.slippage import SlippageEngine
from hades.contexts.execution.application.transaction_manager import TransactionManager
from hades.contexts.execution.domain.exits import ExitPolicy
from hades.contexts.execution.domain.models import OrderRequest, OrderSide
from hades.contexts.execution.infrastructure.price_oracle import StaticPriceOracle
from hades.contexts.notification.application.publisher import NotificationPublisher
from hades.contexts.portfolio.application.portfolio_manager import PortfolioManager
from hades.contexts.portfolio.domain.events import PortfolioUpdated
from hades.shared_kernel.events import InMemoryEventBus

_MINT = "So11111111111111111111111111111111111111112"
_START = 1000.0


def _token() -> TokenRef:
    return TokenRef(mint=TokenMint(address=_MINT), symbol="WSOL")


class _Book:
    """The production wiring, assembled around one in-memory bus."""

    def __init__(self, *, price: str = "1.0", policy: ExitPolicy | None = None) -> None:
        self.bus = InMemoryEventBus()
        self.oracle = StaticPriceOracle({_MINT: Decimal(price)})
        self.portfolio = PortfolioManager(
            starting_balance_usd=_START, mode="paper", event_bus=self.bus
        )
        self.portfolio.register(self.bus)

        async def mode_provider() -> str:
            return "paper"

        self.engine = ExecutionEngine(
            executors={
                "paper": PaperExecutor(
                    slippage_engine=SlippageEngine(base_bps=100, hard_max_bps=500),
                    fee_engine=FeeEngine(sol_price_usd=150.0),
                    price_oracle=self.oracle,
                    latency_ms=0,
                )
            },
            mode_provider=mode_provider,
            order_manager=OrderManager(),
            transaction_manager=TransactionManager(),
            event_bus=self.bus,
            notifier=NotificationPublisher(self.bus),
        )
        self.monitor = PositionMonitor(
            engine=self.engine,
            price_oracle=self.oracle,
            event_bus=self.bus,
            policy=policy
            or ExitPolicy(
                take_profit_pct=40.0, stop_loss_pct=20.0, trailing_enabled=False
            ),
        )
        self.monitor.register(self.bus)

    async def buy(self, notional: str = "100") -> None:
        await self.engine.execute(
            OrderRequest(
                token=_token(),
                side=OrderSide.BUY,
                notional=Money(amount=Decimal(notional)),
                max_slippage_bps=300,
                strategy="momentum",
            )
        )

    def price(self, value: str) -> None:
        self.oracle.set(_MINT, Decimal(value))

    def state(self):
        return self.portfolio.state()


# -- the book moves ---------------------------------------------------------------


async def test_a_rising_price_moves_unrealised_pnl_and_equity() -> None:
    book = _Book(price="1.0")
    await book.buy("100")
    before = book.state()
    assert before.unrealized_pnl_usd == 0.0  # nothing has marked it yet

    book.price("1.20")
    await book.monitor.tick()

    after = book.state()
    assert after.unrealized_pnl_usd > 0
    # Equity is cash + invested + unrealised: it must have moved with the mark.
    assert after.equity_usd > before.equity_usd


async def test_a_falling_price_moves_equity_down() -> None:
    book = _Book(price="1.0")
    await book.buy("100")
    before = book.state().equity_usd

    book.price("0.90")
    await book.monitor.tick()

    assert book.state().unrealized_pnl_usd < 0
    assert book.state().equity_usd < before


async def test_every_mark_produces_a_portfolio_update_and_an_equity_sample() -> None:
    # An equity curve that only samples on open and close is a flat line between
    # trades — which is exactly what the dashboard sparkline used to draw.
    book = _Book(price="1.0")
    updates: list[object] = []

    async def handler(event: object) -> None:
        updates.append(event)

    book.bus.subscribe(PortfolioUpdated.__name__, handler)
    await book.buy("100")
    after_open = len(updates)

    book.price("1.05")
    await book.monitor.tick()
    book.price("1.10")
    await book.monitor.tick()

    # One recompute per mark, on top of the one the open produced.
    assert len(updates) == after_open + 2
    assert book.state().unrealized_pnl_usd > 0


# -- the book closes --------------------------------------------------------------


async def test_hitting_the_take_profit_closes_the_position_and_realises_the_gain() -> None:
    book = _Book(price="1.0")
    await book.buy("100")
    assert book.state().open_positions == 1

    book.price("1.60")
    await book.monitor.tick()

    final = book.state()
    assert final.open_positions == 0
    assert final.realized_pnl_usd > 0
    assert final.unrealized_pnl_usd == 0.0
    # The gain is now in cash, and the book is worth more than it started.
    assert final.equity_usd > _START


async def test_hitting_the_stop_loss_closes_the_position_and_realises_the_loss() -> None:
    book = _Book(price="1.0")
    await book.buy("100")

    book.price("0.70")
    await book.monitor.tick()

    final = book.state()
    assert final.open_positions == 0
    assert final.realized_pnl_usd < 0
    assert final.equity_usd < _START


async def test_a_closed_position_stops_being_tracked_by_the_monitor() -> None:
    book = _Book(price="1.0")
    await book.buy("100")

    book.price("1.60")
    await book.monitor.tick()

    assert book.monitor.tracked == ()


async def test_a_full_round_trip_leaves_the_capital_back_in_cash() -> None:
    book = _Book(price="1.0")
    await book.buy("100")
    assert book.state().cash_usd < _START  # capital is committed

    book.price("1.60")
    await book.monitor.tick()

    final = book.state()
    assert final.invested_usd == 0.0
    assert final.cash_usd == final.equity_usd


async def test_the_realised_pnl_of_a_flat_round_trip_is_a_loss_after_frictions() -> None:
    # Buy and sell at the same price: the frictions are the only thing that moved,
    # so the book must be *down*. A simulation that breaks even here is lying.
    book = _Book(
        price="1.0",
        policy=ExitPolicy(take_profit_pct=0.0, stop_loss_pct=0.0, max_hold_seconds=0.01),
    )
    await book.buy("100")
    await asyncio.sleep(0.02)  # let the time stop come due

    await book.monitor.tick()

    final = book.state()
    assert final.open_positions == 0
    assert final.realized_pnl_usd < 0
    assert final.equity_usd < _START
