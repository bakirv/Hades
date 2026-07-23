"""Ports defined by Wallet Intelligence."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from hades.contexts.common.domain.value_objects import TokenRef, WalletAddress
from hades.contexts.wallet.domain.models import WalletProfile


@runtime_checkable
class WalletProfiler(Protocol):
    """Builds a reputation profile for a single wallet."""

    async def profile(self, address: WalletAddress, *, role: str) -> WalletProfile: ...


@runtime_checkable
class HolderGraphProvider(Protocol):
    """Supplies the current holder set / early buyers for a token."""

    async def deployer(self, token: TokenRef) -> WalletAddress | None: ...

    async def top_holders(self, token: TokenRef, *, limit: int) -> list[WalletAddress]: ...
