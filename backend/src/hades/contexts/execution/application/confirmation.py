"""Confirmation Engine — waits for on-chain confirmation of a live transaction.

Polls the signature status until it reaches the configured commitment or the
timeout elapses, recording the number of attempts, elapsed time and the RPC that
served the confirmation. On timeout the caller (live executor) decides whether to
rotate RPC and retry. Paper mode never uses this — it synthesises an instant
confirmation so the :class:`FillReport` shape stays identical across modes.
"""

from __future__ import annotations

import asyncio
import time

from hades.contexts.execution.domain.models import ConfirmationResult
from hades.contexts.execution.domain.ports import RpcGateway
from hades.shared_kernel.logging import get_logger

_logger = get_logger("execution.confirmation")

_CONFIRMED_STATUSES = frozenset({"confirmed", "finalized"})


class ConfirmationEngine:
    """Confirms a transaction signature within a timeout."""

    def __init__(
        self,
        rpc: RpcGateway,
        *,
        timeout_seconds: float = 30.0,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        self._rpc = rpc
        self._timeout = max(0.1, timeout_seconds)
        self._interval = max(0.05, poll_interval_seconds)

    async def confirm(self, signature: str) -> ConfirmationResult:
        started = time.monotonic()
        deadline = started + self._timeout
        attempts = 0
        last_error: str | None = None

        while time.monotonic() < deadline:
            attempts += 1
            try:
                status = await self._rpc.call(
                    "getSignatureStatuses", [[signature], {"searchTransactionHistory": True}]
                )
                slot, confirmation_status = _parse_status(status)
                if confirmation_status in _CONFIRMED_STATUSES:
                    return ConfirmationResult(
                        confirmed=True,
                        signature=signature,
                        slot=slot,
                        attempts=attempts,
                        elapsed_ms=_elapsed_ms(started),
                        rpc_url=self._rpc.active_endpoint,
                    )
            except Exception as exc:  # a transient RPC error → keep polling
                last_error = str(exc)
                _logger.debug("confirmation_poll_failed", error=last_error)
            await asyncio.sleep(self._interval)

        return ConfirmationResult(
            confirmed=False,
            signature=signature,
            attempts=attempts,
            elapsed_ms=_elapsed_ms(started),
            rpc_url=self._rpc.active_endpoint,
            error=last_error or "confirmation timed out",
        )


def _parse_status(result: object) -> tuple[int | None, str | None]:
    """Extract ``(slot, confirmationStatus)`` from a getSignatureStatuses reply."""
    value = result.get("value") if isinstance(result, dict) else result
    if isinstance(value, list) and value and isinstance(value[0], dict):
        entry = value[0]
        slot = entry.get("slot")
        return (int(slot) if isinstance(slot, int) else None, entry.get("confirmationStatus"))
    return (None, None)


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
