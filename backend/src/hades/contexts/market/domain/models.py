"""Market value objects."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from hades.contexts.common.domain.value_objects import Money, TokenRef
from hades.shared_kernel.domain.base import ValueObject


class MarketSnapshot(ValueObject):
    """A point-in-time market state for a token."""

    token: TokenRef
    captured_at: datetime
    price: Money
    liquidity: Money
    volume_24h: Money
    spread_bps: float
    venue: str  # e.g. "raydium", "jupiter"


class PriceTick(ValueObject):
    """A single price update used to drive position management."""

    token: TokenRef
    at: datetime
    price: Decimal
