"""Live Executor — the only component that ever touches real funds.

Independent from the paper path but satisfying the identical :class:`Executor`
interface. The sequence is deliberate and fail-closed:

    quote → slippage guard → sign → send → confirm → report

Any failure short-circuits to a failed :class:`FillReport` (never a partial or
optimistic success); transient send/confirm failures are retried under the
:class:`RetryEngine` with RPC rotation. Keys never leave the
:class:`TransactionSigner`. This class is wired only when the hard live gate is
enabled — a config file alone can never route orders here (see the Mode Manager).
"""

from __future__ import annotations

import time
from decimal import Decimal

from hades.contexts.common.domain.value_objects import Money
from hades.contexts.execution.application.confirmation import ConfirmationEngine
from hades.contexts.execution.application.fees import FeeEngine
from hades.contexts.execution.application.retry import RetryableError, RetryEngine
from hades.contexts.execution.application.swap_manager import SwapManager
from hades.contexts.execution.domain.models import (
    ExecutionMode,
    FillReport,
    OrderRequest,
    OrderSide,
    OrderStatus,
)
from hades.contexts.execution.domain.ports import RpcGateway, TransactionSigner
from hades.shared_kernel.errors import ValidationError
from hades.shared_kernel.logging import get_logger

_logger = get_logger("execution.live")


class LiveExecutor:
    """Executes a real on-chain swap. Satisfies ``Executor``."""

    def __init__(
        self,
        *,
        swap_manager: SwapManager,
        signer: TransactionSigner,
        confirmation: ConfirmationEngine,
        fee_engine: FeeEngine,
        rpc: RpcGateway,
        retry: RetryEngine,
    ) -> None:
        self._swap = swap_manager
        self._signer = signer
        self._confirmation = confirmation
        self._fees = fee_engine
        self._rpc = rpc
        self._retry = retry

    @property
    def mode(self) -> str:
        return ExecutionMode.LIVE.value

    async def execute(self, request: OrderRequest) -> FillReport:
        started = time.monotonic()
        try:
            return await self._execute(request, started)
        except ValidationError as exc:  # slippage over budget etc. — a clean cancel
            return self._failed(request, str(exc), started)
        except RetryableError as exc:  # exhausted send/confirm retries
            return self._failed(request, str(exc), started)
        except Exception as exc:  # unknown failure → fail closed, never optimistic
            _logger.error("live_execute_error", mint=str(request.token.mint), error=str(exc))
            return self._failed(request, f"unexpected: {exc}", started)

    async def _execute(self, request: OrderRequest, started: float) -> FillReport:
        prepared = await self._swap.prepare(request, owner=self._signer.public_key)

        async def _send(attempt: int) -> str:
            try:
                return await self._signer.sign_and_send(prepared.serialized_tx)
            except Exception as exc:  # a send failure is transient — retry/rotate
                raise RetryableError(f"send failed (attempt {attempt}): {exc}") from exc

        signature = await self._retry.run(_send)
        assert isinstance(signature, str)

        confirmation = await self._confirmation.confirm(signature)
        if not confirmation.confirmed:
            return self._failed(
                request, confirmation.error or "not confirmed", started, signature=signature
            )

        notional = Decimal(str(request.notional.amount))
        fees = self._fees.estimate(notional_usd=notional)
        quantity = _received_quantity(prepared.quote, request.side)
        price = prepared.quote.price if prepared.quote.price > 0 else Decimal(1)
        latency_ms = int((time.monotonic() - started) * 1000)

        _logger.warning(
            "live_fill",
            mint=str(request.token.mint),
            side=request.side.value,
            signature=signature,
            notional_usd=float(notional),
        )
        return FillReport(
            token=request.token,
            side=request.side,
            status=OrderStatus.FILLED,
            filled_quantity=quantity,
            average_price=Money(amount=price),
            fees=fees.as_money(),
            mode=self.mode,
            slippage_bps=int(prepared.quote.price_impact_pct * 100.0),
            latency_ms=latency_ms,
            notional=Money(amount=notional),
            fee_breakdown=fees,
            confirmation=confirmation,
            signature=signature,
        )

    def _failed(
        self, request: OrderRequest, reason: str, started: float, *, signature: str | None = None
    ) -> FillReport:
        return FillReport(
            token=request.token,
            side=request.side,
            status=OrderStatus.FAILED,
            filled_quantity=Decimal(0),
            average_price=Money(amount=Decimal(0)),
            fees=Money(amount=Decimal(0)),
            mode=self.mode,
            latency_ms=int((time.monotonic() - started) * 1000),
            notional=request.notional,
            signature=signature,
            error=reason,
        )


def _received_quantity(quote: object, side: OrderSide) -> Decimal:
    """Tokens received: a BUY receives ``out_amount``; a SELL sold ``in_amount``."""
    out_amount = getattr(quote, "out_amount", Decimal(0))
    in_amount = getattr(quote, "in_amount", Decimal(0))
    return out_amount if side is OrderSide.BUY else in_amount
