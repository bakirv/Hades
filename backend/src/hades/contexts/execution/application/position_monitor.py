"""The Position Monitor — what makes an open position a live thing.

Without this component the platform can only buy. The Execution Engine opens a
position on a filled BUY and would close one on a filled SELL, but nothing ever
issued a SELL and nothing ever re-priced what was already held. The consequences
were not subtle: unrealised PnL sat at exactly zero for the life of every
position, realised PnL never moved because nothing ever closed, and equity —
cash plus invested plus unrealised — stayed pinned to the starting balance
forever. Every number on the portfolio dashboard was real code faithfully
reporting a book that never changed.

This closes that loop. On every tick it:

1. prices each tracked position through the :class:`PriceOracle`;
2. publishes ``PositionUpdated``, which is what moves the Portfolio Manager's
   unrealised PnL, equity, drawdown and equity curve;
3. asks :func:`~hades.contexts.execution.domain.exits.evaluate_exit` whether the
   position should close, and if so places a SELL through the same
   :class:`ExecutionEngine` a normal trade goes through.

Design notes that matter:

* **The exit path is the ordinary execution path.** A monitor-initiated sell is
  built, executed, recorded, notified and turned into ``PositionClosed`` by
  exactly the code a manual sell would use. There is no second, quieter way to
  trade — which is what keeps the audit trail complete.
* **No price, no mark.** A failed price lookup leaves the position untouched
  rather than marking it at a stale or invented number. A broken feed must not be
  able to liquidate the book, so an unpriceable position is simply held.
* **One exit per position.** An in-flight sell sets a flag that survives until
  ``PositionClosed`` arrives, so a position that keeps breaching its stop while
  the order is executing cannot be sold twice.
* **The monitor never decides to open.** Entry stays with the Committee and the
  Risk Manager; this component only ever reduces exposure.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from decimal import Decimal

from hades.contexts.common.domain.value_objects import Money, TokenRef
from hades.contexts.execution.application.engine import ExecutionEngine
from hades.contexts.execution.application.metrics import ExecutionMetrics
from hades.contexts.execution.domain.exits import ExitPolicy, PositionMark, evaluate_exit
from hades.contexts.execution.domain.models import OrderRequest, OrderSide
from hades.contexts.execution.domain.ports import PriceOracle
from hades.contexts.portfolio.domain.events import (
    PositionClosed,
    PositionOpened,
    PositionUpdated,
)
from hades.shared_kernel.domain.events import DomainEvent
from hades.shared_kernel.domain.identifiers import new_id
from hades.shared_kernel.events import EventBus
from hades.shared_kernel.logging import get_logger

_logger = get_logger("execution.position_monitor")


@dataclass
class TrackedPosition:
    """One open position, as the monitor sees it."""

    position_id: str
    token: TokenRef
    entry_price: Decimal
    quantity: Decimal
    notional_usd: Decimal
    peak_price: Decimal
    opened_at: float
    tags: dict[str, str] = field(default_factory=dict)
    #: Set once an exit order is in flight; cleared only by ``PositionClosed``.
    exiting: bool = False

    @property
    def strategy(self) -> str:
        return self.tags.get("strategy", "default")


class PositionMonitor:
    """Marks open positions to market and closes the ones that hit their exit."""

    def __init__(
        self,
        *,
        engine: ExecutionEngine,
        price_oracle: PriceOracle,
        event_bus: EventBus,
        policy: ExitPolicy,
        interval_seconds: float = 5.0,
        max_slippage_bps: int = 300,
        metrics: ExecutionMetrics | None = None,
    ) -> None:
        self._engine = engine
        self._oracle = price_oracle
        self._bus = event_bus
        self._policy = policy
        self._interval = max(0.5, interval_seconds)
        self._max_slippage_bps = max_slippage_bps
        self._metrics = metrics
        self._positions: dict[str, TrackedPosition] = {}
        self._stop = asyncio.Event()

    def register(self, event_bus: EventBus) -> None:
        event_bus.subscribe(PositionOpened.__name__, self._on_opened)
        event_bus.subscribe(PositionClosed.__name__, self._on_closed)

    @property
    def tracked(self) -> tuple[TrackedPosition, ...]:
        return tuple(self._positions.values())

    # -- event handlers -------------------------------------------------------

    async def _on_opened(self, event: DomainEvent) -> None:
        if not isinstance(event, PositionOpened):
            return
        entry = Decimal(str(event.entry_price.amount))
        self._positions[str(event.aggregate_id)] = TrackedPosition(
            position_id=str(event.aggregate_id),
            token=event.token,
            entry_price=entry,
            quantity=Decimal(str(event.quantity)),
            notional_usd=Decimal(str(event.notional.amount)),
            peak_price=entry,
            opened_at=time.monotonic(),
            tags=dict(event.tags),
        )
        self._update_gauge()
        _logger.info(
            "position_tracked",
            position_id=str(event.aggregate_id),
            mint=str(event.token.mint),
            entry_price=float(entry),
            notional_usd=float(event.notional.amount),
        )

    async def _on_closed(self, event: DomainEvent) -> None:
        if not isinstance(event, PositionClosed):
            return
        if self._positions.pop(str(event.aggregate_id), None) is not None:
            self._update_gauge()

    # -- the loop -------------------------------------------------------------

    async def run(self) -> None:
        """Tick until stopped. One failing tick never ends the loop."""
        while not self._stop.is_set():
            try:
                await self.tick()
            except Exception as exc:  # a monitor that dies stops all exits
                _logger.error("position_monitor_tick_failed", error=str(exc))
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
            except TimeoutError:
                continue

    async def stop(self) -> None:
        self._stop.set()

    async def tick(self) -> int:
        """Mark every tracked position once. Returns how many were priced."""
        marked = 0
        # Snapshot first: an exit mutates the dict while we are iterating it.
        for position in list(self._positions.values()):
            if position.exiting:
                continue
            if await self._mark(position):
                marked += 1
        return marked

    # -- internals ------------------------------------------------------------

    async def _mark(self, position: TrackedPosition) -> bool:
        price = await self._price(position.token)
        if price is None:
            if self._metrics:
                self._metrics.marks_unpriced.inc()
            return False

        if price > position.peak_price:
            position.peak_price = price

        unrealized = (price - position.entry_price) * position.quantity
        await self._bus.publish(
            PositionUpdated(
                aggregate_id=position.position_id,
                mark_price=Money(amount=price),
                unrealized_pnl=Money(amount=unrealized),
            )
        )
        if self._metrics:
            self._metrics.marks.inc()

        reason = evaluate_exit(
            PositionMark(
                entry_price=position.entry_price,
                mark_price=price,
                peak_price=position.peak_price,
                held_seconds=time.monotonic() - position.opened_at,
            ),
            self._policy,
        )
        if reason is not None:
            await self._exit(position, price, reason)
        return True

    async def _price(self, token: TokenRef) -> Decimal | None:
        try:
            price = await self._oracle.price_usd(token)
        except Exception as exc:  # a bad feed must never break the loop
            _logger.warning("mark_price_failed", mint=str(token.mint), error=str(exc))
            return None
        if price is None or price <= 0:
            return None
        return Decimal(str(price))

    async def _exit(self, position: TrackedPosition, price: Decimal, reason: str) -> None:
        """Place the closing SELL through the ordinary execution path."""
        # Marked before the await: the flag is what stops the next tick from
        # selling the same position again while this order is still in flight.
        position.exiting = True
        proceeds = position.quantity * price
        _logger.info(
            "position_exit_triggered",
            position_id=position.position_id,
            mint=str(position.token.mint),
            reason=reason,
            entry_price=float(position.entry_price),
            mark_price=float(price),
            expected_proceeds_usd=float(proceeds),
        )
        request = OrderRequest(
            token=position.token,
            side=OrderSide.SELL,
            notional=Money(amount=proceeds),
            max_slippage_bps=self._max_slippage_bps,
            strategy=position.strategy,
            correlation_id=str(new_id()),
            # ``exit_reason`` is what the engine puts on PositionClosed, and what
            # the Risk Manager counts as a daily stop-loss.
            tags={**position.tags, "exit_reason": reason},
        )
        if self._metrics:
            self._metrics.exits.labels(reason=reason).inc()
        try:
            await self._engine.execute(request)
        except Exception as exc:
            # The sell failed. Clear the flag so the next tick can retry — a
            # position stuck in "exiting" would never be closed by anything.
            position.exiting = False
            _logger.error(
                "position_exit_failed",
                position_id=position.position_id,
                mint=str(position.token.mint),
                reason=reason,
                error=str(exc),
            )

    def _update_gauge(self) -> None:
        if self._metrics:
            self._metrics.tracked_positions.set(len(self._positions))


__all__ = ["PositionMonitor", "TrackedPosition"]
