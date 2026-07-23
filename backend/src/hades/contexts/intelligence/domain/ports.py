"""Ports (contracts) the Wallet Intelligence context depends on.

The engines and profilers depend on abstractions only; all I/O (PostgreSQL,
on-chain reads) lives behind these protocols so the domain stays pure and
testable. History is *append-only* everywhere: profiles gain new versions, the
knowledge base and timeline only grow — nothing is ever overwritten in a way that
loses the past.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from hades.contexts.common.domain.value_objects import WalletAddress
from hades.contexts.intelligence.domain.models import (
    Cluster,
    Relationship,
    TimelineEntry,
    WalletProfile,
)


@runtime_checkable
class WalletRepository(Protocol):
    """Loads and stores wallet profiles; keeps every version forever."""

    async def get(self, address: WalletAddress) -> WalletProfile | None: ...

    async def save(self, profile: WalletProfile) -> None:
        """Upsert the current profile *and* append the version to history."""
        ...

    async def top_by_score(
        self, *, limit: int, smart_money_only: bool = False
    ) -> list[WalletProfile]: ...

    async def count(self) -> int: ...


@runtime_checkable
class TimelineStore(Protocol):
    """Append-only per-wallet event timeline."""

    async def append(self, entries: list[TimelineEntry]) -> None: ...

    async def load(self, address: WalletAddress, *, limit: int = 100) -> list[TimelineEntry]: ...


@runtime_checkable
class RelationshipStore(Protocol):
    """The wallet relationship graph (funding / co-holding / clustering edges)."""

    async def add(self, relationships: list[Relationship]) -> None: ...

    async def neighbors(
        self, address: WalletAddress, *, limit: int = 100
    ) -> list[Relationship]: ...


@runtime_checkable
class ClusterStore(Protocol):
    """Persists detected clusters and resolves a wallet's cluster."""

    async def save(self, cluster: Cluster) -> None: ...

    async def for_wallet(self, address: WalletAddress) -> Cluster | None: ...

    async def recent(self, *, limit: int = 50) -> list[Cluster]: ...


@runtime_checkable
class KnowledgeBase(Protocol):
    """Append-only ledger of every intelligence event, for audit and training.

    Never overwrites: each record is an immutable observation of what the system
    learned and when. Over years this becomes the platform's richest asset.
    """

    async def record(
        self, *, address: str, kind: str, payload: dict[str, object], at: datetime
    ) -> None: ...


@runtime_checkable
class WalletChainReader(Protocol):
    """Minimal on-chain reads the observation assembler needs.

    Best-effort: return empty on failure so the assembler degrades to "less
    observed", never crashes. Kept deliberately small so it can be satisfied by
    the Scanner's existing RPC reader without duplicating parsing.
    """

    async def top_holder_addresses(self, mint: str, *, limit: int = 20) -> list[tuple[str, float]]:
        """Return ``(owner, pct_supply)`` for the largest holders."""
        ...

    async def funders(self, wallet: str, *, limit: int = 10) -> list[str]:
        """Return wallets that funded ``wallet`` (SOL in), most-recent first."""
        ...
