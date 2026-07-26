"""Price oracles — what a token is worth right now, in USD.

Two things depend on this being real. The :class:`~hades.contexts.execution.
application.paper_executor.PaperExecutor` turns a USD notional into a token
quantity, and the :class:`~hades.contexts.execution.application.position_monitor.
PositionMonitor` marks open positions to market. With no oracle wired both
degrade to a unit price, which means every paper fill is priced at $1 and every
open position shows exactly zero unrealised PnL forever.

The adapter never raises: a price it cannot vouch for comes back as ``None`` and
the caller decides. Returning a stale or invented number would be worse than
returning nothing, because both callers can degrade honestly but neither can
detect a lie.
"""

from __future__ import annotations

import time
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from hades.contexts.common.domain.value_objects import TokenRef
from hades.shared_kernel.logging import get_logger

_logger = get_logger("execution.price_oracle")

_DEFAULT_URL = "https://api.dexscreener.com/latest/dex/tokens"


class DexScreenerPriceOracle:
    """Reads DexScreener's token endpoint for a USD price. Satisfies ``PriceOracle``.

    A mint usually trades in several pairs at slightly different prices. We take
    the price from the **deepest** pool rather than the first one returned: a thin
    pool's last trade is the number easiest to move, and marking a book against it
    would let a few dollars of someone else's volume swing our equity.

    Prices are cached for a few seconds. The monitor polls every open position on
    every tick, so without a cache a book of twenty positions would issue twenty
    HTTP calls every few seconds and get itself rate-limited — at which point the
    portfolio silently stops moving again.
    """

    def __init__(
        self,
        *,
        base_url: str = _DEFAULT_URL,
        timeout_seconds: float = 10.0,
        ttl_seconds: float = 5.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._ttl = max(0.0, ttl_seconds)
        self._client = client
        self._owns_client = client is None
        self._cache: dict[str, tuple[float, Decimal]] = {}

    async def price_usd(self, token: TokenRef) -> Decimal | None:
        mint = str(token.mint)
        cached = self._cached(mint)
        if cached is not None:
            return cached

        client = self._ensure_client()
        try:
            response = await client.get(f"{self._base}/{mint}", timeout=self._timeout)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # an oracle must never raise into the caller
            _logger.warning("price_lookup_failed", mint=mint, error=str(exc))
            return None

        price = _best_price(payload)
        if price is None:
            _logger.debug("price_unavailable", mint=mint)
            return None
        if self._ttl:
            self._cache[mint] = (time.monotonic(), price)
        return price

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    # -- internals ------------------------------------------------------------

    def _cached(self, mint: str) -> Decimal | None:
        entry = self._cache.get(mint)
        if entry is None:
            return None
        stamped, price = entry
        if time.monotonic() - stamped > self._ttl:
            self._cache.pop(mint, None)
            return None
        return price

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(headers={"accept": "application/json"})
        return self._client


class StaticPriceOracle:
    """A fixed price book. For tests and offline runs; never for a live book."""

    def __init__(self, prices: dict[str, Decimal] | None = None) -> None:
        self._prices = dict(prices or {})

    def set(self, mint: str, price: Decimal) -> None:
        self._prices[mint] = price

    async def price_usd(self, token: TokenRef) -> Decimal | None:
        return self._prices.get(str(token.mint))


def _best_price(payload: Any) -> Decimal | None:
    """Pick the USD price from the deepest pair in a DexScreener response."""
    if not isinstance(payload, dict):
        return None
    pairs = payload.get("pairs")
    if not isinstance(pairs, list) or not pairs:
        return None

    best: tuple[float, Decimal] | None = None
    for pair in pairs:
        if not isinstance(pair, dict):
            continue
        price = _decimal(pair.get("priceUsd"))
        if price is None or price <= 0:
            continue
        liquidity = pair.get("liquidity")
        depth = 0.0
        if isinstance(liquidity, dict):
            depth = _float(liquidity.get("usd"))
        if best is None or depth > best[0]:
            best = (depth, price)
    return best[1] if best else None


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


__all__ = ["DexScreenerPriceOracle", "StaticPriceOracle"]
