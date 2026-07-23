"""Ports defined by the Market Engine."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from hades.contexts.common.domain.value_objects import TokenRef
from hades.contexts.market.domain.models import MarketSnapshot, PriceTick


@runtime_checkable
class MarketDataProvider(Protocol):
    """Point-in-time market data for scoring."""

    async def snapshot(self, token: TokenRef) -> MarketSnapshot: ...


@runtime_checkable
class PriceFeed(Protocol):
    """Live price stream for position management."""

    def subscribe(self, token: TokenRef) -> AsyncIterator[PriceTick]: ...

    async def unsubscribe(self, token: TokenRef) -> None: ...
