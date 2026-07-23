"""Order Manager — the single source of truth for order lifecycle.

Tracks every order the engine creates through its states (pending → submitted →
confirming → filled, or failed/cancelled). Trazabilidad is never lost: terminal
orders are retained (bounded ring) so the dashboard and audit can always answer
"what happened to this order?". State lives in memory (like the Portfolio
Manager's book) and is mirrored best-effort to an :class:`OrderStore`.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from hades.contexts.execution.domain.models import (
    FillReport,
    OrderRequest,
    OrderState,
    is_terminal,
)
from hades.contexts.execution.domain.ports import OrderStore
from hades.shared_kernel.domain.identifiers import new_id
from hades.shared_kernel.logging import get_logger

_logger = get_logger("execution.orders")
_MAX_TRACKED = 5_000


@dataclass
class OrderRecord:
    """The mutable lifecycle record for one order."""

    order_id: str
    mint: str
    symbol: str | None
    side: str
    mode: str
    notional_usd: float
    max_slippage_bps: int
    strategy: str
    correlation_id: str | None
    state: OrderState = OrderState.PENDING
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    filled_quantity: float | None = None
    average_price: float | None = None
    fee_usd: float | None = None
    slippage_bps: int | None = None
    signature: str | None = None
    latency_ms: int | None = None
    reason: str | None = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "mint": self.mint,
            "symbol": self.symbol,
            "side": self.side,
            "mode": self.mode,
            "state": self.state.value,
            "notional_usd": self.notional_usd,
            "max_slippage_bps": self.max_slippage_bps,
            "strategy": self.strategy,
            "correlation_id": self.correlation_id,
            "filled_quantity": self.filled_quantity,
            "average_price": self.average_price,
            "fee_usd": self.fee_usd,
            "slippage_bps": self.slippage_bps,
            "signature": self.signature,
            "latency_ms": self.latency_ms,
            "reason": self.reason,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class OrderManager:
    """Owns order lifecycle state; mirrors terminal orders to a store."""

    def __init__(self, *, store: OrderStore | None = None) -> None:
        self._orders: OrderedDict[str, OrderRecord] = OrderedDict()
        self._store = store

    def create(self, request: OrderRequest, *, mode: str) -> OrderRecord:
        record = OrderRecord(
            order_id=str(new_id()),
            mint=str(request.token.mint),
            symbol=request.token.symbol,
            side=request.side.value,
            mode=mode,
            notional_usd=float(request.notional.amount),
            max_slippage_bps=request.max_slippage_bps,
            strategy=request.strategy,
            correlation_id=request.correlation_id,
        )
        self._orders[record.order_id] = record
        self._evict()
        return record

    def transition(self, record: OrderRecord, state: OrderState) -> None:
        record.state = state
        record.updated_at = time.time()

    async def complete(self, record: OrderRecord, fill: FillReport) -> None:
        record.state = OrderState.FILLED if fill.filled else OrderState.FAILED
        record.filled_quantity = float(fill.filled_quantity)
        record.average_price = float(fill.average_price.amount)
        record.fee_usd = float(fill.fees.amount)
        record.slippage_bps = fill.slippage_bps
        record.signature = fill.signature
        record.latency_ms = fill.latency_ms
        record.reason = fill.error
        record.updated_at = time.time()
        await self._persist(record)

    async def fail(self, record: OrderRecord, reason: str) -> None:
        record.state = OrderState.FAILED
        record.reason = reason
        record.updated_at = time.time()
        await self._persist(record)

    async def cancel(self, record: OrderRecord, reason: str) -> None:
        record.state = OrderState.CANCELLED
        record.reason = reason
        record.updated_at = time.time()
        await self._persist(record)

    # -- read models ---------------------------------------------------------

    def recent(self, *, limit: int = 50) -> list[dict[str, Any]]:
        records = list(self._orders.values())[-limit:]
        return [r.snapshot() for r in reversed(records)]

    def open_orders(self) -> list[dict[str, Any]]:
        return [r.snapshot() for r in self._orders.values() if not is_terminal(r.state)]

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self._orders.values():
            out[r.state.value] = out.get(r.state.value, 0) + 1
        out["total"] = len(self._orders)
        return out

    # -- internals -----------------------------------------------------------

    async def _persist(self, record: OrderRecord) -> None:
        if self._store is None:
            return
        try:
            await self._store.save(record.snapshot())
        except Exception as exc:  # persistence is best-effort, never blocking
            _logger.debug("order_persist_failed", order_id=record.order_id, error=str(exc))

    def _evict(self) -> None:
        while len(self._orders) > _MAX_TRACKED:
            self._orders.popitem(last=False)
