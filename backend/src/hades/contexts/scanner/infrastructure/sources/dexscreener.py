"""DexScreener discovery adapter.

DexScreener aggregates pairs across many Solana DEXes, which makes it a good
broad discovery net. We read its search endpoint and surface Solana pairs, using
the base token as the candidate mint and the pair's USD liquidity.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import httpx

from hades.contexts.scanner.domain.ports import RawTokenCandidate
from hades.contexts.scanner.infrastructure.sources.base import (
    HttpPollingSource,
    make_candidate,
)

_DEFAULT_URL = "https://api.dexscreener.com/latest/dex/search?q=solana"


class DexScreenerSource(HttpPollingSource):
    """Polls DexScreener's search endpoint for Solana pairs."""

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
        return "dexscreener"

    @property
    def url(self) -> str:
        return self._url

    def parse(self, payload: Any) -> Iterable[RawTokenCandidate]:
        pairs = payload.get("pairs") or [] if isinstance(payload, dict) else []
        for pair in pairs:
            if not isinstance(pair, dict) or pair.get("chainId") != "solana":
                continue
            base = pair.get("baseToken") or {}
            mint = base.get("address")
            if not mint:
                continue
            liquidity = (pair.get("liquidity") or {}).get("usd") or 0.0
            candidate = make_candidate(
                mint=str(mint),
                source=self.name,
                liquidity_usd=float(liquidity),
                symbol=base.get("symbol"),
                name=base.get("name"),
            )
            if candidate is not None:
                yield candidate
