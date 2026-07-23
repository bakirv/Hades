"""In-memory stores for the order/transaction ledger.

The execution runtime keeps its authoritative order/transaction state in memory
(like the Portfolio Manager's book) and publishes snapshots to Redis for the
dashboard. These in-memory stores are the default binding for the
:class:`OrderStore`/:class:`TransactionStore` ports; a Postgres binding that
writes the durable ``trades`` ledger can replace them without touching the
engine (it depends only on the ports).
"""

from __future__ import annotations

from collections import deque
from typing import Any


class InMemoryOrderStore:
    """A bounded ring of order snapshots. Satisfies ``OrderStore``."""

    def __init__(self, *, maxlen: int = 5_000) -> None:
        self._items: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._by_id: dict[str, dict[str, Any]] = {}

    async def save(self, snapshot: dict[str, Any]) -> None:
        order_id = str(snapshot.get("order_id"))
        if order_id in self._by_id:
            self._by_id[order_id].update(snapshot)
            return
        self._by_id[order_id] = dict(snapshot)
        self._items.append(self._by_id[order_id])

    async def recent(self, *, limit: int = 50) -> list[dict[str, Any]]:
        return list(reversed(list(self._items)[-limit:]))


class InMemoryTransactionStore:
    """A bounded ring of transaction detail. Satisfies ``TransactionStore``."""

    def __init__(self, *, maxlen: int = 5_000) -> None:
        self._items: deque[dict[str, Any]] = deque(maxlen=maxlen)

    async def record(self, detail: dict[str, Any]) -> None:
        self._items.append(dict(detail))

    async def recent(self, *, limit: int = 50) -> list[dict[str, Any]]:
        return list(reversed(list(self._items)[-limit:]))
