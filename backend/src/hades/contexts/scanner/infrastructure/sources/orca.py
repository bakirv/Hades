"""Orca discovery adapter.

Orca's Whirlpools are concentrated-liquidity pools. We read the whirlpool list
and surface the non-quote token of each pool, using the pool's TVL as coarse
liquidity.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import httpx

from hades.contexts.common.domain.value_objects import Money, TokenMint
from hades.contexts.scanner.domain.models import RawPool
from hades.contexts.scanner.domain.ports import RawTokenCandidate
from hades.contexts.scanner.infrastructure.sources.base import (
    HttpPollingSource,
    make_candidate,
    pick_base_mint,
)

_DEFAULT_URL = "https://api.mainnet.orca.so/v1/whirlpool/list"


class OrcaSource(HttpPollingSource):
    """Polls Orca's whirlpool list."""

    def __init__(
        self,
        *,
        url: str = _DEFAULT_URL,
        poll_interval_seconds: float = 5.0,
        timeout_seconds: float = 12.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            poll_interval_seconds=poll_interval_seconds,
            timeout_seconds=timeout_seconds,
            client=client,
        )
        self._url = url

    @property
    def name(self) -> str:
        return "orca"

    @property
    def url(self) -> str:
        return self._url

    def parse(self, payload: Any) -> Iterable[RawTokenCandidate]:
        pools = payload.get("whirlpools") if isinstance(payload, dict) else None
        for pool in pools or []:
            if not isinstance(pool, dict):
                continue
            token_a = (pool.get("tokenA") or {}).get("mint")
            token_b = (pool.get("tokenB") or {}).get("mint")
            base = pick_base_mint(token_a, token_b)
            if not base:
                continue
            tvl = float(pool.get("tvl") or 0.0)
            quote = token_b if base == token_a else token_a
            raw_pool = _pool(str(pool.get("address")), base, quote, tvl)
            candidate = make_candidate(
                mint=str(base), source=self.name, liquidity_usd=tvl, pool=raw_pool
            )
            if candidate is not None:
                yield candidate


def _pool(address: str, base: str, quote: str | None, tvl: float) -> RawPool | None:
    if not address:
        return None
    try:
        return RawPool(
            address=address,
            dex="orca",
            base_mint=TokenMint(address=base),
            quote_mint=TokenMint(address=quote) if quote else None,
            liquidity=Money(amount=tvl),
        )
    except ValueError:
        return None
