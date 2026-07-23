"""Feature-engine value objects."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from hades.contexts.common.domain.value_objects import TokenRef
from hades.shared_kernel.domain.base import ValueObject


class FeatureSet(ValueObject):
    """A computed feature vector for a token at a point in time.

    Kept as an open ``dict`` of named numeric features so the schema can grow to
    hundreds of variables without a breaking change. ``schema_version`` lets the
    Learning Engine reconcile features computed under different definitions.
    """

    token: TokenRef
    computed_at: datetime
    schema_version: int = 1
    values: dict[str, float] = Field(default_factory=dict)

    def get(self, name: str, default: float = 0.0) -> float:
        return self.values.get(name, default)


class MarketPoint(ValueObject):
    """One historical observation used by the technical/time-series extractors."""

    at: datetime
    price: float
    volume: float = 0.0
    liquidity: float = 0.0
    buys: int = 0
    sells: int = 0


class HolderInfo(ValueObject):
    """Holder-distribution snapshot (from an on-chain holder graph)."""

    count: int = 0
    new_holders: int = 0
    active_wallets: int = 0
    recurring_wallets: int = 0
    top10_share_pct: float = 0.0
    gini: float = 0.0
    prev_count: int = 0


class PoolInfo(ValueObject):
    """Liquidity-pool snapshot used by the pool extractor."""

    size_usd: float = 0.0
    depth_usd: float = 0.0
    concentration: float = 0.0
    lp_holders: int = 0
    lp_locked: bool = False
    lock_duration_seconds: float = 0.0
    liquidity_change_pct: float = 0.0
    lp_change_pct: float = 0.0


class FeatureInputs(ValueObject):
    """The raw, cleaned data bundle a token's features are computed from.

    The Feature Engine transforms *this* into the (hundreds of) feature values.
    Every field is optional / defaulted so a token with partial data still yields
    a vector — missing inputs simply produce neutral features, never an error.
    """

    token: TokenRef
    now: datetime
    created_at: datetime | None = None
    first_swap_at: datetime | None = None
    first_holder_at: datetime | None = None
    first_pool_at: datetime | None = None
    first_liquidity_at: datetime | None = None
    # Current market state.
    price: float = 0.0
    market_cap: float = 0.0
    fdv: float = 0.0
    liquidity: float = 0.0
    tvl: float = 0.0
    spread_bps: float = 0.0
    slippage_bps: float = 0.0
    volume: float = 0.0
    buy_volume: float = 0.0
    sell_volume: float = 0.0
    buyers: int = 0
    sellers: int = 0
    trades_1m: int = 0
    trades_5m: int = 0
    trades_15m: int = 0
    trades_1h: int = 0
    # Time series (oldest -> newest) and structured sub-states.
    history: tuple[MarketPoint, ...] = ()
    holders: HolderInfo | None = None
    pool: PoolInfo | None = None
