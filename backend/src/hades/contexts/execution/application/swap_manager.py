"""Swap Manager — turns an order into a quoted, buildable on-chain swap (live).

Wraps the :class:`QuoteProvider` so the live executor deals in domain terms: ask
for a quote for a USD notional against the wallet's quote mint (SOL/USDC), and
get back a :class:`Quote` plus the serialized, unsigned transaction ready to
sign. It enforces the slippage budget at quote time: a quote whose price impact
exceeds the order's tolerance is rejected before anything is signed or sent.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from hades.contexts.execution.domain.models import OrderRequest, OrderSide, Quote
from hades.contexts.execution.domain.ports import QuoteProvider
from hades.shared_kernel.errors import ValidationError
from hades.shared_kernel.logging import get_logger

_logger = get_logger("execution.swap")

# Canonical Solana quote mints. The wallet trades the token against one of these.
_WSOL_MINT = "So11111111111111111111111111111111111111112"
_USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


@dataclass(frozen=True)
class PreparedSwap:
    quote: Quote
    serialized_tx: bytes


class SwapManager:
    """Quotes and prepares a swap transaction for the live path."""

    def __init__(
        self,
        provider: QuoteProvider,
        *,
        quote_mint: str = _USDC_MINT,
        sol_price_usd: float = 150.0,
    ) -> None:
        self._provider = provider
        self._quote_mint = quote_mint
        self._sol_price = Decimal(str(sol_price_usd))

    async def prepare(self, request: OrderRequest, *, owner: str) -> PreparedSwap:
        token_mint = str(request.token.mint)
        notional_usd = Decimal(str(request.notional.amount))

        # A BUY spends the quote mint to receive the token; a SELL does the reverse.
        if request.side is OrderSide.BUY:
            input_mint, output_mint = self._quote_mint, token_mint
            amount = self._to_quote_amount(notional_usd)
        else:
            input_mint, output_mint = token_mint, self._quote_mint
            amount = notional_usd  # SELL sizing is handled upstream; pass notional

        quote = await self._provider.quote(
            input_mint=input_mint,
            output_mint=output_mint,
            amount=amount,
            slippage_bps=request.max_slippage_bps,
        )

        impact_bps = quote.price_impact_pct * 100.0
        if impact_bps > request.max_slippage_bps:
            raise ValidationError(
                "quote price impact exceeds slippage budget",
                context={
                    "impact_bps": round(impact_bps, 2),
                    "max_bps": request.max_slippage_bps,
                    "mint": token_mint,
                },
            )

        serialized = await self._provider.build_swap_tx(quote, owner=owner)
        _logger.info(
            "swap_prepared",
            mint=token_mint,
            side=request.side.value,
            impact_bps=round(impact_bps, 2),
            route=quote.route,
        )
        return PreparedSwap(quote=quote, serialized_tx=serialized)

    def _to_quote_amount(self, notional_usd: Decimal) -> Decimal:
        """Convert a USD notional to the quote-mint amount (SOL vs USDC)."""
        if self._quote_mint == _WSOL_MINT:
            return notional_usd / self._sol_price
        return notional_usd  # USDC ≈ 1 USD
