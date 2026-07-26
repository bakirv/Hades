"""Paper Executor — a faithful simulation of a real fill.

Paper mode is worthless if it lies about costs, so this executor refuses to use
ideal prices. It grounds the fill in a real price (via a :class:`PriceOracle`),
applies a *dynamically estimated* slippage against the trade direction, charges
the same fees the live path would, and waits a simulated latency + confirmation
before returning. It never signs a transaction and never touches the wallet. The
returned :class:`FillReport` is byte-for-byte the same shape a live fill produces
— that identity is the whole point of the paper/live seam.
"""

from __future__ import annotations

import asyncio
import time
from decimal import Decimal

from hades.contexts.common.domain.value_objects import Money
from hades.contexts.execution.application.fees import FeeEngine
from hades.contexts.execution.application.slippage import SlippageEngine
from hades.contexts.execution.domain.models import (
    ConfirmationResult,
    ExecutionMode,
    FillReport,
    OrderRequest,
    OrderSide,
    OrderStatus,
    SlippageContext,
)
from hades.contexts.execution.domain.ports import PriceOracle
from hades.shared_kernel.domain.identifiers import new_id
from hades.shared_kernel.logging import get_logger

_logger = get_logger("execution.paper")

#: Floor for a computed fill price — a price of zero would make the quantity
#: division blow up, and no real market prints one.
_MIN_PRICE = Decimal("0.000000000000000001")


class PaperExecutor:
    """Simulates an order under realistic conditions. Satisfies ``Executor``."""

    def __init__(
        self,
        *,
        slippage_engine: SlippageEngine,
        fee_engine: FeeEngine,
        price_oracle: PriceOracle | None = None,
        latency_ms: int = 250,
        base_slippage_bps: int = 80,
    ) -> None:
        self._slippage = slippage_engine
        self._fees = fee_engine
        self._oracle = price_oracle
        self._latency_ms = max(0, latency_ms)
        self._base_slippage_bps = max(0, base_slippage_bps)

    @property
    def mode(self) -> str:
        return ExecutionMode.PAPER.value

    async def execute(self, request: OrderRequest) -> FillReport:
        started = time.monotonic()

        # Simulate submission + network latency before the fill lands.
        if self._latency_ms:
            await asyncio.sleep(self._latency_ms / 1000.0)

        notional = Decimal(str(request.notional.amount))
        price = await self._reference_price(request)

        estimate = self._slippage.estimate(
            SlippageContext(
                liquidity_usd=_as_float(request.tags.get("liquidity_usd")),
                volatility_pct=_as_float(request.tags.get("volatility_pct")),
                spread_bps=_as_float(request.tags.get("spread_bps")),
                notional_usd=float(notional),
                dex=request.tags.get("dex", "unknown"),
            ),
            order_max_bps=request.max_slippage_bps,
        )
        slip_bps = min(estimate.recommended_bps, request.max_slippage_bps)

        # Slippage moves the effective price against the taker. Which side of the
        # notional it lands on differs, and the difference is the whole point:
        #
        #   BUY  — the order size is the cash you spend. It is fixed; slippage
        #          buys you *fewer tokens* for it.
        #   SELL — the order size is the market value of what you are selling.
        #          The tokens are fixed; slippage means you *receive less cash*.
        #
        # Modelling a sell like a buy (cash received == order size) would make
        # exit slippage free, and a simulation that hands you a costless exit
        # reports profits the real market would never have paid.
        slip_factor = Decimal(slip_bps) / Decimal(10_000)
        if request.side is OrderSide.BUY:
            fill_price = max(price * (Decimal(1) + slip_factor), _MIN_PRICE)
            quantity = (notional / fill_price).quantize(_MIN_PRICE)
            filled_notional = notional
        else:
            fill_price = max(price * (Decimal(1) - slip_factor), _MIN_PRICE)
            quantity = (notional / price).quantize(_MIN_PRICE)
            filled_notional = quantity * fill_price

        fees = self._fees.estimate(notional_usd=filled_notional)
        latency_ms = int((time.monotonic() - started) * 1000)

        _logger.info(
            "paper_fill",
            mint=str(request.token.mint),
            side=request.side.value,
            notional_usd=float(filled_notional),
            slippage_bps=slip_bps,
            fee_usd=float(fees.total_usd),
        )
        return FillReport(
            token=request.token,
            side=request.side,
            status=OrderStatus.FILLED,
            filled_quantity=quantity,
            average_price=Money(amount=fill_price),
            fees=fees.as_money(),
            mode=self.mode,
            slippage_bps=slip_bps,
            latency_ms=latency_ms,
            notional=Money(amount=filled_notional),
            fee_breakdown=fees,
            confirmation=ConfirmationResult(
                confirmed=True,
                signature=f"paper-{new_id()}",
                attempts=1,
                elapsed_ms=latency_ms,
                rpc_url="paper",
            ),
            signature=f"paper-{new_id()}",
        )

    async def _reference_price(self, request: OrderRequest) -> Decimal:
        """Real price when an oracle is wired; otherwise a unit price (qty == USD).

        A unit price keeps the simulation honest about *costs* (slippage/fees are
        applied on the notional) without inventing a token price we do not have.
        """
        if self._oracle is not None:
            try:
                price = await self._oracle.price_usd(request.token)
                if price is not None and price > 0:
                    return Decimal(str(price))
            except Exception as exc:  # oracle failure → fall back, never crash
                _logger.debug("paper_price_failed", error=str(exc))
        return Decimal(1)


def _as_float(value: str | None) -> float:
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0
