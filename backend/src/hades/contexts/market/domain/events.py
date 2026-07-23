"""Domain events emitted by the Market Engine."""

from __future__ import annotations

from hades.contexts.market.domain.models import MarketSnapshot, PriceTick
from hades.shared_kernel.domain.events import DomainEvent


class MarketSnapshotUpdated(DomainEvent):
    """A fresh market snapshot is available for a token."""

    aggregate_type: str = "token"
    snapshot: MarketSnapshot


class PriceTicked(DomainEvent):
    """A price update for a token with an open (or candidate) position."""

    aggregate_type: str = "token"
    tick: PriceTick
