"""On-chain reader adapters for Wallet Intelligence.

The intelligence assembler needs only two cheap reads (a token's largest holders
and a wallet's funders). Rather than duplicate the Scanner's RPC parsing, the
:class:`SecurityReaderAdapter` wraps any object that already exposes the Security
Engine's on-chain reader shape (``get_largest_holders`` + ``get_funders``) and
projects it onto the small :class:`WalletChainReader` port. The in-memory reader
serves tests.
"""

from __future__ import annotations

from typing import Any, Protocol


class _SecurityReaderLike(Protocol):
    """Structural view of the Scanner/Security on-chain reader we reuse."""

    async def get_largest_holders(self, mint: str, *, limit: int = 20) -> list[Any]: ...

    async def get_funders(self, wallet: str, *, limit: int = 25) -> list[str]: ...


class SecurityReaderAdapter:
    """Projects a Security-style on-chain reader onto ``WalletChainReader``."""

    def __init__(self, reader: _SecurityReaderLike) -> None:
        self._reader = reader

    async def top_holder_addresses(self, mint: str, *, limit: int = 20) -> list[tuple[str, float]]:
        holders = await self._reader.get_largest_holders(mint, limit=limit)
        result: list[tuple[str, float]] = []
        for holder in holders:
            owner = getattr(holder, "owner", None)
            pct = getattr(holder, "pct", 0.0)
            if isinstance(owner, str):
                result.append((owner, float(pct)))
        return result

    async def funders(self, wallet: str, *, limit: int = 10) -> list[str]:
        return await self._reader.get_funders(wallet, limit=limit)


class InMemoryChainReader:
    """Deterministic on-chain reader for tests."""

    def __init__(
        self,
        *,
        holders: dict[str, list[tuple[str, float]]] | None = None,
        funders: dict[str, list[str]] | None = None,
    ) -> None:
        self._holders = holders or {}
        self._funders = funders or {}

    async def top_holder_addresses(self, mint: str, *, limit: int = 20) -> list[tuple[str, float]]:
        return self._holders.get(mint, [])[:limit]

    async def funders(self, wallet: str, *, limit: int = 10) -> list[str]:
        return self._funders.get(wallet, [])[:limit]
