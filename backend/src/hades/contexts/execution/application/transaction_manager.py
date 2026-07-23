"""Transaction Manager — records the on-chain (and simulated) transaction trail.

For every executed order it keeps the transaction detail the audit and dashboard
need: signature, slot, block time, fees, confirmation time, the RPC that served
it, attempts and any error. Live transactions carry a real signature; paper
"transactions" carry a simulated id so the ledger shape is uniform. State is an
in-memory bounded ring mirrored best-effort to a :class:`TransactionStore`.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any

from hades.contexts.execution.domain.models import FillReport
from hades.contexts.execution.domain.ports import TransactionStore
from hades.shared_kernel.logging import get_logger

_logger = get_logger("execution.transactions")
_MAX_TRACKED = 5_000


class TransactionManager:
    """Keeps the transaction detail trail; mirrors it to a store."""

    def __init__(self, *, store: TransactionStore | None = None) -> None:
        self._txns: deque[dict[str, Any]] = deque(maxlen=_MAX_TRACKED)
        self._store = store

    async def record(self, *, order_id: str, fill: FillReport) -> dict[str, Any]:
        confirmation = fill.confirmation
        detail: dict[str, Any] = {
            "order_id": order_id,
            "mode": fill.mode,
            "mint": str(fill.token.mint),
            "symbol": fill.token.symbol,
            "side": fill.side.value,
            "status": fill.status.value,
            "signature": fill.signature,
            "fee_usd": float(fill.fees.amount),
            "slippage_bps": fill.slippage_bps,
            "latency_ms": fill.latency_ms,
            "slot": confirmation.slot if confirmation else None,
            "block_time": confirmation.block_time if confirmation else None,
            "confirmation_ms": confirmation.elapsed_ms if confirmation else None,
            "attempts": confirmation.attempts if confirmation else None,
            "rpc_url": confirmation.rpc_url if confirmation else None,
            "error": fill.error,
            "recorded_at": time.time(),
        }
        if fill.fee_breakdown is not None:
            fb = fill.fee_breakdown
            detail["fees"] = {
                "network_usd": float(fb.network_fee_usd),
                "priority_usd": float(fb.priority_fee_usd),
                "dex_usd": float(fb.dex_fee_usd),
                "priority_fee_microlamports": fb.priority_fee_microlamports,
            }
        self._txns.append(detail)
        if self._store is not None:
            try:
                await self._store.record(detail)
            except Exception as exc:  # best-effort persistence
                _logger.debug("txn_persist_failed", order_id=order_id, error=str(exc))
        return detail

    def recent(self, *, limit: int = 50) -> list[dict[str, Any]]:
        items = list(self._txns)[-limit:]
        return list(reversed(items))

    def stats(self) -> dict[str, Any]:
        txns = list(self._txns)
        if not txns:
            return {
                "count": 0,
                "avg_latency_ms": 0.0,
                "avg_slippage_bps": 0.0,
                "total_fees_usd": 0.0,
            }
        latencies = [t["latency_ms"] for t in txns if t.get("latency_ms") is not None]
        slippages = [t["slippage_bps"] for t in txns if t.get("slippage_bps") is not None]
        fees = [t["fee_usd"] for t in txns if t.get("fee_usd") is not None]
        return {
            "count": len(txns),
            "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
            "avg_slippage_bps": round(sum(slippages) / len(slippages), 2) if slippages else 0.0,
            "total_fees_usd": round(sum(fees), 6) if fees else 0.0,
        }
